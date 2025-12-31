from threading import Lock

class JobStates:
    def __init__(self):
        self._lock = Lock()
        self._initialized = False
        
        # Job state definitions
        self.PENDING = "Pending"
        self.RUNNING = "Running" 
        self.COMPLETED = "Completed"
        self.FAILED = "Failed"
        self.CANCELLED = "Cancelled"
        
        # Valid state transitions
        self._valid_transitions = {
            self.PENDING: [self.RUNNING, self.CANCELLED],
            self.RUNNING: [self.COMPLETED, self.FAILED, self.CANCELLED],
            self.COMPLETED: [],  # Terminal state
            self.FAILED: [self.PENDING],  # Can be retried
            self.CANCELLED: []  # Terminal state
        }
        
        # States that indicate job is finished
        self._terminal_states = {self.COMPLETED, self.FAILED, self.CANCELLED}
        
        # States that indicate job is active
        self._active_states = {self.PENDING, self.RUNNING}
    
    def initialize(self):
        """Initialize job states - called at startup"""
        with self._lock:
            if not self._initialized:
                self._initialized = True
                from output import output
                output.info("Job states initialized successfully")
    
    def is_valid_transition(self, from_state: str, to_state: str) -> bool:
        """Check if a state transition is valid"""
        return to_state in self._valid_transitions.get(from_state, [])
    
    def is_terminal(self, state: str) -> bool:
        """Check if a state is terminal (job finished)"""
        return state in self._terminal_states
    
    def is_active(self, state: str) -> bool:
        """Check if a state is active (job not finished)"""
        return state in self._active_states
    
    def is_retryable(self, state: str) -> bool:
        """Check if a job in this state can be retried"""
        return state == self.FAILED
    
    def get_all_states(self) -> list:
        """Get all available job states"""
        return [self.PENDING, self.RUNNING, self.COMPLETED, self.FAILED, self.CANCELLED]
    
    def get_terminal_states(self) -> set:
        """Get all terminal states"""
        return self._terminal_states.copy()
    
    def get_active_states(self) -> set:
        """Get all active states"""
        return self._active_states.copy()

# Create singleton instance
states = JobStates()