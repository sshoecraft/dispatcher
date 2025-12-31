#!/usr/bin/env python3

"""
Authentication service module for Dispatcher.
Handles JWT tokens, password hashing, and multi-source authentication (local, OS, LDAP).
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple
from passlib.context import CryptContext
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
import secrets
import pam
import pwd
from ldap3 import Server, Connection, ALL, NTLM
from output import output

# Import models
from models import User, UserRole, UserSession

# Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 hours

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security scheme
security = HTTPBearer()


class LoginRequest(BaseModel):
    """Login request model"""
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    auth_source: Optional[str] = Field(default="local", pattern=r'^(local|os|ldap)$')


class TokenResponse(BaseModel):
    """Token response model"""
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]


class UserCreateRequest(BaseModel):
    """User creation request model"""
    username: str = Field(..., min_length=3, max_length=100)
    password: Optional[str] = Field(None, min_length=6)
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: str = Field(default="viewer", pattern=r'^(admin|operator|viewer|auditor)$')
    auth_source: str = Field(default="local", pattern=r'^(local|os|ldap)$')
    
    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
    
    def __init__(self, **data):
        # Convert empty string password to None for non-local auth sources
        if 'password' in data and data['password'] == '' and data.get('auth_source') in ['os', 'ldap']:
            data['password'] = None
        super().__init__(**data)


class UserUpdateRequest(BaseModel):
    """User update request model"""
    username: Optional[str] = Field(None, min_length=3, max_length=100)
    password: Optional[str] = Field(None, min_length=6)
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = Field(None, pattern=r'^(admin|operator|viewer|auditor)$')
    auth_source: Optional[str] = Field(None, pattern=r'^(local|os|ldap)$')
    is_active: Optional[bool] = None
    
    def __init__(self, **data):
        # Convert empty string password to None for non-local auth sources
        if 'password' in data and data['password'] == '' and data.get('auth_source') in ['os', 'ldap']:
            data['password'] = None
        super().__init__(**data)


class AuthService:
    """Authentication service for handling user authentication and authorization"""
    
    def __init__(self):
        self.ldap_config = None
        self._load_ldap_config()
    
    def _load_ldap_config(self):
        """Load LDAP configuration from environment or config file"""
        self.ldap_config = {
            'server': os.getenv('LDAP_SERVER', ''),
            'port': int(os.getenv('LDAP_PORT', '389')),
            'use_ssl': os.getenv('LDAP_USE_SSL', 'false').lower() == 'true',
            'base_dn': os.getenv('LDAP_BASE_DN', ''),
            'bind_dn': os.getenv('LDAP_BIND_DN', ''),
            'bind_password': os.getenv('LDAP_BIND_PASSWORD', ''),
            'user_search_base': os.getenv('LDAP_USER_SEARCH_BASE', ''),
            'user_search_filter': os.getenv('LDAP_USER_SEARCH_FILTER', '(uid={username})'),
            'group_search_base': os.getenv('LDAP_GROUP_SEARCH_BASE', ''),
            'group_search_filter': os.getenv('LDAP_GROUP_SEARCH_FILTER', '(memberUid={username})'),
            'admin_group': os.getenv('LDAP_ADMIN_GROUP', 'admins'),
            'operator_group': os.getenv('LDAP_OPERATOR_GROUP', 'operators'),
        }
    
    def validate_os_user(self, username: str) -> Optional[dict]:
        """Validate OS user exists and get user information"""
        try:
            user_info = pwd.getpwnam(username)
            # Extract full name from GECOS field (format: "Full Name,office,phone,other")
            full_name = user_info.pw_gecos.split(',')[0] if user_info.pw_gecos else username
            
            return {
                'username': username,
                'full_name': full_name,
                'uid': user_info.pw_uid,
                'gid': user_info.pw_gid,
                'home': user_info.pw_dir,
                'shell': user_info.pw_shell
            }
        except KeyError:
            output.warning(f"OS user {username} does not exist")
            return None
    
    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt"""
        return pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against a hash"""
        return pwd_context.verify(plain_password, hashed_password)
    
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT access token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    
    def decode_token(self, token: str) -> Dict[str, Any]:
        """Decode and validate a JWT token"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        except JWTError:
            return None
    
    def authenticate_local(self, session: Session, username: str, password: str) -> Optional[User]:
        """Authenticate using local database credentials"""
        user = session.query(User).filter(
            User.username == username,
            User.auth_source == 'local'
        ).first()
        
        if not user or not user.password_hash:
            return None
        
        if not self.verify_password(password, user.password_hash):
            return None
        
        return user
    
    def authenticate_os(self, session: Session, username: str, password: str) -> Optional[User]:
        """Authenticate using OS/PAM credentials"""
        # Use PAM to authenticate
        p = pam.pam()
        if not p.authenticate(username, password):
            output.warning(f"OS authentication failed for user {username}")
            return None
        
        # Get OS user info
        os_user_info = self.validate_os_user(username)
        if not os_user_info:
            output.warning(f"OS user {username} does not exist in system")
            return None
        
        # Check if user exists in database
        user = session.query(User).filter(
            User.username == username,
            User.auth_source == 'os'
        ).first()
        
        if not user:
            # Auto-create user with OS info if auth succeeds
            user = User(
                username=username,
                full_name=os_user_info['full_name'],
                auth_source='os',
                role='viewer',
                is_active=True
            )
            session.add(user)
            session.commit()
            output.info(f"Auto-created OS user {username} ({os_user_info['full_name']}) with viewer role")
        else:
            # Update user info from OS
            user.full_name = os_user_info['full_name']
            session.commit()
        
        return user
    
    def authenticate_ldap(self, session: Session, username: str, password: str) -> Optional[User]:
        """Authenticate using LDAP/AD credentials"""
        if not self.ldap_config['server']:
            output.warning("LDAP not configured")
            return None
        
        try:
            # Create LDAP server connection
            server = Server(
                self.ldap_config['server'],
                port=self.ldap_config['port'],
                use_ssl=self.ldap_config['use_ssl'],
                get_info=ALL
            )
            
            # Try to bind with user credentials
            user_dn = f"uid={username},{self.ldap_config['user_search_base']}"
            conn = Connection(server, user_dn, password, auto_bind=True)
            
            # Authentication successful, get user info
            conn.search(
                self.ldap_config['user_search_base'],
                self.ldap_config['user_search_filter'].format(username=username),
                attributes=['cn', 'mail', 'memberOf']
            )
            
            if not conn.entries:
                conn.unbind()
                return None
            
            ldap_user = conn.entries[0]
            full_name = str(ldap_user.cn) if hasattr(ldap_user, 'cn') else username
            email = str(ldap_user.mail) if hasattr(ldap_user, 'mail') else None
            
            # Determine role from LDAP groups
            role = 'viewer'  # default role
            if hasattr(ldap_user, 'memberOf'):
                groups = [str(g) for g in ldap_user.memberOf]
                if any(self.ldap_config['admin_group'] in g for g in groups):
                    role = 'admin'
                elif any(self.ldap_config['operator_group'] in g for g in groups):
                    role = 'operator'
            
            conn.unbind()
            
            # Check if user exists in database
            user = session.query(User).filter(
                User.username == username,
                User.auth_source == 'ldap'
            ).first()
            
            if not user:
                # Auto-create user from LDAP
                user = User(
                    username=username,
                    email=email,
                    full_name=full_name,
                    auth_source='ldap',
                    role=role,
                    is_active=True
                )
                session.add(user)
                session.commit()
                output.info(f"Auto-created LDAP user {username} with role {role}")
            else:
                # Update user info from LDAP
                user.email = email
                user.full_name = full_name
                user.role = role
                session.commit()
            
            return user
            
        except Exception as e:
            output.error(f"LDAP authentication error: {e}")
            return None
    
    def authenticate(self, session: Session, username: str, password: str, auth_source: str = "local") -> Optional[User]:
        """Authenticate user using specified authentication source"""
        user = None
        
        if auth_source == "local":
            user = self.authenticate_local(session, username, password)
        elif auth_source == "os":
            user = self.authenticate_os(session, username, password)
        elif auth_source == "ldap":
            user = self.authenticate_ldap(session, username, password)
        else:
            output.warning(f"Unknown authentication source: {auth_source}")
            return None
        
        if user and user.is_active:
            # Update last login time
            user.last_login = datetime.now(timezone.utc)
            session.commit()
            return user
        
        return None
    
    def create_user_session(self, session: Session, user: User, token: str) -> UserSession:
        """Create a user session record"""
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        user_session = UserSession(
            user_id=user.id,
            token=token,
            expires_at=expires_at
        )
        session.add(user_session)
        session.commit()
        
        return user_session
    
    def invalidate_token(self, session: Session, token: str) -> bool:
        """Invalidate a token by removing it from sessions"""
        user_session = session.query(UserSession).filter(
            UserSession.token == token
        ).first()
        
        if user_session:
            session.delete(user_session)
            session.commit()
            return True
        
        return False
    
    def get_current_user(self, session: Session, token: str) -> Optional[User]:
        """Get current user from token"""
        # Decode token
        payload = self.decode_token(token)
        if not payload:
            return None
        
        username = payload.get("sub")
        if not username:
            return None
        
        # Check if token exists in sessions and is not expired
        user_session = session.query(UserSession).filter(
            UserSession.token == token,
            UserSession.expires_at > datetime.now(timezone.utc)
        ).first()
        
        if not user_session:
            return None
        
        # Get user
        user = session.query(User).filter(
            User.username == username,
            User.is_active == True
        ).first()
        
        return user
    
    def check_permission(self, user: User, permission: str) -> bool:
        """Check if user has a specific permission based on role"""
        # Role-based permission mapping
        role_permissions = {
            'admin': ['*'],  # Admin has all permissions
            'operator': [
                'jobs.view', 'jobs.create', 'jobs.cancel', 'jobs.retry', 'jobs.delete',
                'workers.view', 'workers.create', 'workers.update', 'workers.delete',
                'queues.view', 'queues.create', 'queues.update', 'queues.delete',
                'specs.view', 'specs.create', 'specs.update', 'specs.delete',
                'settings.view', 'settings.update'
            ],
            'viewer': [
                'jobs.view', 'workers.view', 'queues.view', 'specs.view', 'settings.view'
            ],
            'auditor': [
                'jobs.view', 'workers.view', 'queues.view', 'specs.view', 
                'settings.view', 'logs.view', 'audit.view'
            ]
        }
        
        user_permissions = role_permissions.get(user.role, [])
        
        # Check for wildcard permission
        if '*' in user_permissions:
            return True
        
        return permission in user_permissions
    
    def initialize_default_admin(self, session: Session):
        """Create default admin user if no users exist"""
        # Check if any users exist
        user_count = session.query(User).count()
        if user_count > 0:
            return
        
        # Create default admin user
        admin_user = User(
            username='admin',
            password_hash=self.hash_password('admin'),
            role='admin',
            auth_source='local',
            is_active=True,
            full_name='System Administrator',
            email='admin@local'
        )
        session.add(admin_user)
        
        # Create default roles
        roles = [
            UserRole(
                name='admin',
                description='Full system administrator access',
                permissions=['*']
            ),
            UserRole(
                name='operator',
                description='Can manage jobs, workers, queues, and specs',
                permissions=[
                    'jobs.*', 'workers.*', 'queues.*', 'specs.*', 'settings.view', 'settings.update'
                ]
            ),
            UserRole(
                name='viewer',
                description='Read-only access to all resources',
                permissions=['*.view']
            ),
            UserRole(
                name='auditor',
                description='Read-only access with audit trail capabilities',
                permissions=['*.view', 'logs.view', 'audit.view']
            )
        ]
        
        for role in roles:
            existing_role = session.query(UserRole).filter(UserRole.name == role.name).first()
            if not existing_role:
                session.add(role)
        
        session.commit()
        output.info("Created default admin user (username: admin, password: admin)")
        output.warning("IMPORTANT: Change the default admin password immediately!")


# Create global auth service instance
auth = AuthService()


# FastAPI dependency to get current user
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """FastAPI dependency to get current authenticated user"""
    from db import db
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No authentication credentials provided",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    with db.get_session() as session:
        user = auth.get_current_user(session, token)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Detach from session to avoid issues
        session.expunge(user)
        
    return user


# FastAPI dependency to require specific permission
def require_permission(permission: str):
    """FastAPI dependency to require specific permission"""
    async def permission_checker(current_user: User = Depends(get_current_user)):
        if not auth.check_permission(current_user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {permission}"
            )
        return current_user
    return permission_checker


# FastAPI dependency to require specific role
def require_role(roles: list):
    """FastAPI dependency to require specific role(s)"""
    async def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient role. Required one of: {', '.join(roles)}"
            )
        return current_user
    return role_checker