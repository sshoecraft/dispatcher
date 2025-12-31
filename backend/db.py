
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
from threading import Lock
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional
import json
import os
from info import info
from output import output

# Try to import Azure identity - optional dependency
try:
    from azure.identity import DefaultAzureCredential
    AZURE_IDENTITY_AVAILABLE = True
except ImportError:
    AZURE_IDENTITY_AVAILABLE = False

# Pydantic model for database configuration updates
class DatabaseConfigUpdateRequest(BaseModel):
    """Request model for updating database configuration"""
    DB_TYPE: Optional[str] = Field(None, pattern=r'^(postgresql|sqlite|mysql)$')
    PG_HOST: Optional[str] = None
    PG_DB: Optional[str] = None
    PG_PORT: Optional[str] = None
    PG_USER: Optional[str] = None
    PG_PWD: Optional[str] = None
    PG_SCHEMA: Optional[str] = None
    USE_MANAGED_IDENTITY: Optional[str] = Field(None, pattern=r'^(true|false)$')
    PG_MANAGED_IDENTITY_USER: Optional[str] = None

class Database:
    def __init__(self):
        self.opened = False
        self.engine = None
        self.SessionLocal = None
        self._lock = Lock()
        self._config_path = None

    @property
    def config_path(self):
        """Get the config path, creating it if needed"""
        if self._config_path is None:
            self._config_path = Path(info.prefix) / 'etc' / 'database.json'
        return self._config_path

    def open(self):
        """Initialize database connection - called at startup"""
        with self._lock:
            if not self.opened:
                try:
                    db_config = self._read_config()
                    self.create_connection(db_config)
                    self.opened = True
                    output.info("Database initialized successfully")
                except Exception as e:
                    output.error(f"Failed to initialize database: {e}")
                    raise

    def close(self):
        """Close database connection - called at shutdown"""
        with self._lock:
            if self.opened and self.engine:
                self.engine.dispose()
                output.info("Database connection closed")
                self.opened = False
                self.engine = None
                self.SessionLocal = None

    def get_config(self):
        """Get database configuration for API endpoints"""
        try:
            with open(self.config_path, 'r') as f:
                config_data = json.load(f)
                
            return config_data
        except FileNotFoundError:
            return {"database": {}}
        except json.JSONDecodeError as e:
            output.error(f"Invalid JSON in database config file: {e}")
            return {"database": {}}
        except Exception as e:
            output.error(f"Error reading database config: {e}")
            return {"database": {}}

    def put_config(self, config_updates):
        """Update database configuration in database.json file"""
        
        try:
            # Read existing config or create new one
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    config_data = json.load(f)
            else:
                config_data = {"database": {}}
            
            # Ensure parent directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Update values in database section
            if 'database' not in config_data:
                config_data['database'] = {}
                
            for key, value in config_updates.items():
                if key in config_data['database']:
                    config_data['database'][key]['value'] = value
                else:
                    # Create new entry with default structure
                    config_data['database'][key] = {
                        'value': value,
                        'is_sensitive': False,
                        'description': f'{key} configuration',
                        'default_value': '',
                        'is_required': False,
                        'validation_pattern': None
                    }
            
            # Write updated config
            with open(self.config_path, 'w') as f:
                json.dump(config_data, f, indent=2)
                
            output.info(f"Database configuration updated in {self.config_path}")
            return True
            
        except Exception as e:
            output.error(f"Error writing database config: {e}")
            return False

    def _read_config(self):
        """Read database configuration for internal connection use"""
        try:
            with open(self.config_path, 'r') as f:
                config_data = json.load(f)
                
            # Extract database section
            db_config = config_data.get('database', {})
            
            # Convert to flat dictionary format
            result = {}
            for key, value_info in db_config.items():
                result[key] = value_info.get('value', value_info.get('default_value', ''))
                
            if result:
                return result
            else:
                output.warning("No database config found, using default SQLite")
                
        except FileNotFoundError:
            output.warning(f"Database config file not found at {self.config_path}, using default SQLite")
        except json.JSONDecodeError as e:
            output.error(f"Invalid JSON in database config file: {e}, using default SQLite")
        except Exception as e:
            output.error(f"Error reading database config: {e}, using default SQLite")
            
        # Default to SQLite when no config file exists
        return {
            'PG_HOST': os.getenv('PG_HOST', 'localhost'),
            'PG_DB': os.getenv('PG_DB', 'orchestrator'),
            'PG_PORT': os.getenv('PG_PORT', '5432'),
            'PG_USER': os.getenv('PG_USER', ''),
            'PG_PWD': os.getenv('PG_PWD', ''),
            'PG_SCHEMA': os.getenv('PG_SCHEMA', 'public'),
            'PG_MANAGED_IDENTITY_USER': os.getenv('PG_MANAGED_IDENTITY_USER'),
            'DB_TYPE': os.getenv('DB_TYPE', 'sqlite'),  # Default to SQLite
            'USE_MANAGED_IDENTITY': os.getenv('USE_MANAGED_IDENTITY', 'false')
        }

    def create_connection(self, db_config):
        """Create database connection with given config"""
        db_type = db_config.get('DB_TYPE', 'postgresql').lower()
        
        if db_type == 'sqlite':
            # SQLite configuration - use info.prefix/lib
            db_path = Path(info.prefix) / 'lib' / f'{info.name}.db'
            DATABASE_URL = f"sqlite:///{db_path}"
            
            def sqlite_fk_pragma(dbapi_connection, connection_record):
                """Enable foreign key constraints for SQLite"""
                dbapi_connection.execute('PRAGMA foreign_keys=ON')
            
            self.engine = create_engine(
                DATABASE_URL, 
                connect_args={"check_same_thread": False}
            )
            
            # Enable foreign key constraints for all SQLite connections
            from sqlalchemy import event
            event.listen(self.engine, 'connect', sqlite_fk_pragma)
            
            os.environ['DB_TYPE'] = 'sqlite'
            output.info(f"Using SQLite database at {db_path} with foreign key constraints enabled")
            
        elif db_type == 'mysql':
            # MySQL configuration
            host = db_config.get('PG_HOST', 'localhost')
            db = db_config.get('PG_DB', 'orchestrator')
            port = db_config.get('PG_PORT', '3306')
            user = db_config.get('PG_USER', '')
            pwd = db_config.get('PG_PWD', '')
            
            if user and pwd:
                DATABASE_URL = f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}"
            else:
                DATABASE_URL = f"mysql+pymysql://{host}:{port}/{db}"
                
            self.engine = create_engine(DATABASE_URL)
            os.environ['DB_TYPE'] = 'mysql'
            output.info(f"Connected to MySQL at {host}:{port}/{db}")
            
        else:  # postgresql (default)
            # PostgreSQL configuration
            pg_host = db_config.get('PG_HOST', 'localhost')
            pg_db = db_config.get('PG_DB', 'orchestrator')
            pg_port = db_config.get('PG_PORT', '5432')
            pg_user = db_config.get('PG_USER', '')
            pg_pwd = db_config.get('PG_PWD', '')
            pg_schema = db_config.get('PG_SCHEMA', 'public')
            use_managed_identity = db_config.get('USE_MANAGED_IDENTITY', 'false').lower() == 'true'
            
            if use_managed_identity:
                # Managed identity authentication
                managed_identity_user = db_config.get('PG_MANAGED_IDENTITY_USER')
                
                if not managed_identity_user:
                    raise ValueError("PG_MANAGED_IDENTITY_USER is required when USE_MANAGED_IDENTITY is true")
                
                if AZURE_IDENTITY_AVAILABLE:
                    try:
                        output.info("Attempting Azure managed identity authentication")
                        credential = DefaultAzureCredential()
                        token = credential.get_token("https://ossrdbms-aad.database.windows.net/")
                        
                        DATABASE_URL = f"postgresql://{managed_identity_user}:{token.token}@{pg_host}:{pg_port}/{pg_db}?sslmode=require&options=-csearch_path%3D{pg_schema}"
                        output.info(f"Using Azure managed identity authentication for user: {managed_identity_user}")
                        
                    except Exception as e:
                        output.error(f"Failed to get Azure managed identity token: {e}")
                        sslmode = "disable" if pg_host in ["localhost", "127.0.0.1"] else "require"
                        DATABASE_URL = f"postgresql://{pg_host}:{pg_port}/{pg_db}?sslmode={sslmode}&options=-csearch_path%3D{pg_schema}"
                        output.warning("Falling back to connection without credentials")
                else:
                    output.error("Azure managed identity requested but azure-identity library not available")
                    sslmode = "disable" if pg_host in ["localhost", "127.0.0.1"] else "require"
                    DATABASE_URL = f"postgresql://{pg_host}:{pg_port}/{pg_db}?sslmode={sslmode}&options=-csearch_path%3D{pg_schema}"
            elif pg_user and pg_pwd:
                # Traditional username/password authentication
                sslmode = "disable" if pg_host in ["localhost", "127.0.0.1"] else "require"
                DATABASE_URL = f"postgresql://{pg_user}:{pg_pwd}@{pg_host}:{pg_port}/{pg_db}?sslmode={sslmode}&options=-csearch_path%3D{pg_schema}"
                output.info("Using traditional PostgreSQL authentication")
            else:
                # No credentials provided
                sslmode = "disable" if pg_host in ["localhost", "127.0.0.1"] else "require"
                DATABASE_URL = f"postgresql://{pg_host}:{pg_port}/{pg_db}?sslmode={sslmode}&options=-csearch_path%3D{pg_schema}"
                output.warning("No PostgreSQL credentials provided - connection may fail")
            
            self.engine = create_engine(DATABASE_URL)
            os.environ['DB_TYPE'] = 'postgresql'
            output.info(f"Connected to PostgreSQL at {pg_host}:{pg_port}/{pg_db}")

        # Create a configured "Session" class
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def reload_connection(self):
        """Reload database connection with updated config"""
        with self._lock:
            try:
                # Close existing connections
                if self.engine:
                    self.engine.dispose()
                    output.info("Disposed existing database connections")
                
                # Reload config and reconnect
                db_config = self._read_config()
                self.create_connection(db_config)
                output.info("Database connection reloaded successfully")
                return True
            except Exception as e:
                output.error(f"Failed to reload database connection: {e}")
                return False

    @contextmanager
    def get_session(self):
        """Context manager for database sessions"""
        if not self.opened or not self.SessionLocal:
            raise RuntimeError("Database not initialized. Call db.open() first.")
            
        session = self.SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def get_dependency(self):
        """FastAPI dependency for database sessions"""
        with self.get_session() as session:
            yield session

db = Database()
