from threading import Lock

class QueueStrategies:
    def __init__(self):
        self._lock = Lock()
        self._initialized = False
        
        # Queue dispatch strategy definitions
        self.ROUND_ROBIN = "round_robin"
        self.LEAST_LOADED = "least_loaded"
        self.RANDOM = "random"
        self.PRIORITY = "priority"
        
        # Default strategy
        self._default_strategy = self.ROUND_ROBIN
        
        # Available strategies for validation
        self._available_strategies = {
            self.ROUND_ROBIN,
            self.LEAST_LOADED, 
            self.RANDOM,
            self.PRIORITY
        }
    
    def initialize(self):
        """Initialize queue strategies - called at startup"""
        with self._lock:
            if not self._initialized:
                self._initialized = True
                from output import output
                output.info("Queue strategies initialized successfully")
    
    def is_valid_strategy(self, strategy: str) -> bool:
        """Check if a strategy is valid"""
        return strategy in self._available_strategies
    
    def get_default_strategy(self) -> str:
        """Get the default strategy"""
        return self._default_strategy
    
    def get_all_strategies(self) -> list:
        """Get all available strategies"""
        return list(self._available_strategies)
    
    def get_strategy_description(self, strategy: str) -> str:
        """Get human-readable description of a strategy"""
        descriptions = {
            self.ROUND_ROBIN: "Distribute jobs evenly across workers in rotation",
            self.LEAST_LOADED: "Send jobs to the worker with the least current load",
            self.RANDOM: "Randomly select a worker for each job",
            self.PRIORITY: "Select workers based on priority assignment"
        }
        return descriptions.get(strategy, "Unknown strategy")

# Create singleton instance
strategies = QueueStrategies()