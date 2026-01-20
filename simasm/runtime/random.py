"""
runtime/random.py

Random number generation for SimASM simulations.

Provides:
- RandomStream: Individual random stream with seed control
- RandomRegistry: Manages multiple named streams

Key features:
- Reproducible sequences via seeding
- Multiple independent streams (for arrival, service, etc.)
- Common distributions for DES (exponential, uniform, triangular, etc.)
- Reset capability for multiple replications

Usage in SimASM:
    import Random as rnd
    
    rnd.exponential(mean)      # Exponential with given mean
    rnd.uniform(a, b)          # Uniform between a and b
    rnd.triangular(a, b, c)    # Triangular with mode c
"""

import random
import math
from typing import Optional, Dict, List

from simasm.log.logger import get_logger

logger = get_logger(__name__)


class RandomError(Exception):
    """Raised when random operations fail."""
    pass


class RandomStream:
    """
    Individual random number stream with seed control.
    
    Each stream maintains its own state, allowing independent
    sequences for different purposes (arrivals, service times, etc.).
    
    Usage:
        stream = RandomStream(seed=42)
        value = stream.exponential(10.0)  # Mean 10
        stream.reset()  # Restart sequence
    """
    
    def __init__(self, seed: Optional[int] = None):
        """
        Initialize random stream.
        
        Args:
            seed: Optional seed for reproducibility. If None, uses system entropy.
        """
        self._initial_seed = seed
        self._rng = random.Random(seed)
        logger.debug(f"Created RandomStream with seed={seed}")
    
    @property
    def seed(self) -> Optional[int]:
        """Return the initial seed (None if not set)."""
        return self._initial_seed
    
    def set_seed(self, seed: int) -> None:
        """
        Set new seed and reset the stream.
        
        Args:
            seed: New seed value
        """
        self._initial_seed = seed
        self._rng.seed(seed)
        logger.debug(f"RandomStream seed set to {seed}")
    
    def reset(self) -> None:
        """
        Reset stream to initial seed.
        
        Restarts the random sequence from the beginning.
        Useful for running multiple replications.
        """
        if self._initial_seed is not None:
            self._rng.seed(self._initial_seed)
            logger.debug(f"RandomStream reset to seed {self._initial_seed}")
        else:
            logger.warning("RandomStream reset called but no initial seed was set")
    
    # =========================================================================
    # Continuous Distributions
    # =========================================================================
    
    def uniform(self, a: float, b: float) -> float:
        """
        Uniform distribution on [a, b].
        
        Args:
            a: Lower bound (inclusive)
            b: Upper bound (inclusive)
        
        Returns:
            Random value uniformly distributed between a and b
            
        Example:
            rnd.uniform(0, 1)      # Standard uniform
            rnd.uniform(5, 10)     # Uniform between 5 and 10
        """
        if a > b:
            raise RandomError(f"uniform: a ({a}) must be <= b ({b})")
        return self._rng.uniform(a, b)
    
    def exponential(self, mean: float) -> float:
        """
        Exponential distribution with given mean.
        
        Note: Python's random.expovariate takes rate (1/mean),
        but we use mean directly for convenience in DES.
        
        Args:
            mean: Mean of the distribution (must be > 0)
        
        Returns:
            Random value from exponential distribution
            
        Example:
            rnd.exponential(10.0)  # Mean interarrival time of 10
        """
        if mean <= 0:
            raise RandomError(f"exponential: mean ({mean}) must be > 0")
        # expovariate takes lambda (rate), not mean
        return self._rng.expovariate(1.0 / mean)
    
    def normal(self, mean: float, std: float) -> float:
        """
        Normal (Gaussian) distribution.
        
        Args:
            mean: Mean of the distribution
            std: Standard deviation (must be >= 0)
        
        Returns:
            Random value from normal distribution
            
        Example:
            rnd.normal(100, 15)  # IQ-like distribution
        """
        if std < 0:
            raise RandomError(f"normal: std ({std}) must be >= 0")
        return self._rng.gauss(mean, std)
    
    def triangular(self, low: float, high: float, mode: float) -> float:
        """
        Triangular distribution.
        
        Args:
            low: Lower bound
            high: Upper bound
            mode: Most likely value (peak)
        
        Returns:
            Random value from triangular distribution
            
        Example:
            rnd.triangular(1, 5, 3)  # Min 1, max 5, most likely 3
        """
        if not (low <= mode <= high):
            raise RandomError(f"triangular: must have low <= mode <= high, got {low}, {mode}, {high}")
        return self._rng.triangular(low, high, mode)
    
    def lognormal(self, mean: float, std: float) -> float:
        """
        Log-normal distribution.
        
        Note: Parameters are mean and std of the underlying normal,
        not of the log-normal itself.
        
        Args:
            mean: Mean of the underlying normal distribution
            std: Standard deviation of the underlying normal
        
        Returns:
            Random value from log-normal distribution
        """
        if std < 0:
            raise RandomError(f"lognormal: std ({std}) must be >= 0")
        return self._rng.lognormvariate(mean, std)
    
    def weibull(self, alpha: float, beta: float) -> float:
        """
        Weibull distribution.
        
        Args:
            alpha: Scale parameter (> 0)
            beta: Shape parameter (> 0)
        
        Returns:
            Random value from Weibull distribution
        """
        if alpha <= 0:
            raise RandomError(f"weibull: alpha ({alpha}) must be > 0")
        if beta <= 0:
            raise RandomError(f"weibull: beta ({beta}) must be > 0")
        return self._rng.weibullvariate(alpha, beta)
    
    def gamma(self, alpha: float, beta: float) -> float:
        """
        Gamma distribution.
        
        Args:
            alpha: Shape parameter (> 0)
            beta: Scale parameter (> 0)
        
        Returns:
            Random value from gamma distribution
        """
        if alpha <= 0:
            raise RandomError(f"gamma: alpha ({alpha}) must be > 0")
        if beta <= 0:
            raise RandomError(f"gamma: beta ({beta}) must be > 0")
        return self._rng.gammavariate(alpha, beta)
    
    def beta(self, alpha: float, beta: float) -> float:
        """
        Beta distribution on [0, 1].
        
        Args:
            alpha: Shape parameter (> 0)
            beta: Shape parameter (> 0)
        
        Returns:
            Random value from beta distribution
        """
        if alpha <= 0:
            raise RandomError(f"beta: alpha ({alpha}) must be > 0")
        if beta <= 0:
            raise RandomError(f"beta: beta ({beta}) must be > 0")
        return self._rng.betavariate(alpha, beta)
    
    # =========================================================================
    # Discrete Distributions
    # =========================================================================
    
    def randint(self, a: int, b: int) -> int:
        """
        Random integer in [a, b] (inclusive).
        
        Args:
            a: Lower bound (inclusive)
            b: Upper bound (inclusive)
        
        Returns:
            Random integer between a and b
            
        Example:
            rnd.randint(1, 6)  # Die roll
        """
        if a > b:
            raise RandomError(f"randint: a ({a}) must be <= b ({b})")
        return self._rng.randint(a, b)
    
    def choice(self, seq: List) -> any:
        """
        Random choice from sequence.
        
        Args:
            seq: Non-empty sequence to choose from
        
        Returns:
            Randomly selected element
            
        Example:
            rnd.choice(["red", "green", "blue"])
        """
        if len(seq) == 0:
            raise RandomError("choice: sequence is empty")
        return self._rng.choice(seq)
    
    def bernoulli(self, p: float) -> bool:
        """
        Bernoulli trial (coin flip with probability p).
        
        Args:
            p: Probability of True (0 <= p <= 1)
        
        Returns:
            True with probability p, False otherwise
            
        Example:
            if rnd.bernoulli(0.7):  # 70% chance
                ...
        """
        if not (0 <= p <= 1):
            raise RandomError(f"bernoulli: p ({p}) must be in [0, 1]")
        return self._rng.random() < p
    
    def geometric(self, p: float) -> int:
        """
        Geometric distribution (number of trials until first success).
        
        Args:
            p: Probability of success on each trial (0 < p <= 1)
        
        Returns:
            Number of trials (>= 1)
            
        Example:
            attempts = rnd.geometric(0.3)  # Attempts until success
        """
        if not (0 < p <= 1):
            raise RandomError(f"geometric: p ({p}) must be in (0, 1]")
        # Inverse transform sampling
        return int(math.ceil(math.log(1.0 - self._rng.random()) / math.log(1.0 - p)))
    
    def poisson(self, lam: float) -> int:
        """
        Poisson distribution.
        
        Args:
            lam: Mean (lambda, must be > 0)
        
        Returns:
            Random non-negative integer
            
        Example:
            arrivals = rnd.poisson(5.0)  # Arrivals per hour
        """
        if lam <= 0:
            raise RandomError(f"poisson: lambda ({lam}) must be > 0")
        # Simple algorithm for small lambda
        L = math.exp(-lam)
        k = 0
        p = 1.0
        while p > L:
            k += 1
            p *= self._rng.random()
        return k - 1
    
    # =========================================================================
    # Utility
    # =========================================================================
    
    def random(self) -> float:
        """
        Standard uniform [0, 1).
        
        Returns:
            Random float in [0, 1)
        """
        return self._rng.random()
    
    def shuffle(self, lst: List) -> None:
        """
        Shuffle list in place.
        
        Args:
            lst: List to shuffle (modified in place)
        """
        self._rng.shuffle(lst)
    
    def sample(self, population: List, k: int) -> List:
        """
        Random sample without replacement.
        
        Args:
            population: Sequence to sample from
            k: Number of items to sample
        
        Returns:
            List of k randomly selected items
        """
        if k < 0:
            raise RandomError(f"sample: k ({k}) must be >= 0")
        if k > len(population):
            raise RandomError(f"sample: k ({k}) exceeds population size ({len(population)})")
        return self._rng.sample(population, k)


class RandomRegistry:
    """
    Registry of named random streams.
    
    Manages multiple independent random streams for different purposes
    (e.g., arrivals, service times, routing decisions).
    
    Usage:
        registry = RandomRegistry()
        registry.create("arrivals", seed=42)
        registry.create("service", seed=123)
        
        arrival_time = registry.get("arrivals").exponential(10)
        service_time = registry.get("service").exponential(8)
        
        # For new replication
        registry.reset_all()
    """
    
    def __init__(self):
        """Initialize empty registry."""
        self._streams: Dict[str, RandomStream] = {}
        self._seeds: Dict[str, int] = {}  # Track seeds for reset
        logger.debug("Created RandomRegistry")
    
    def create(self, name: str, seed: Optional[int] = None) -> RandomStream:
        """
        Create a new named random stream.
        
        Args:
            name: Unique name for the stream
            seed: Optional seed for reproducibility
        
        Returns:
            The created RandomStream
            
        Raises:
            RandomError: If name already exists
        """
        if name in self._streams:
            raise RandomError(f"Stream '{name}' already exists")
        
        stream = RandomStream(seed)
        self._streams[name] = stream
        if seed is not None:
            self._seeds[name] = seed
        
        logger.debug(f"Created stream '{name}' with seed={seed}")
        return stream
    
    def get(self, name: str) -> RandomStream:
        """
        Get stream by name.
        
        Args:
            name: Name of the stream
        
        Returns:
            The RandomStream
            
        Raises:
            RandomError: If stream doesn't exist
        """
        if name not in self._streams:
            raise RandomError(f"Stream '{name}' not found")
        return self._streams[name]
    
    def exists(self, name: str) -> bool:
        """Check if stream exists."""
        return name in self._streams
    
    def set_seed(self, name: str, seed: int) -> None:
        """
        Set seed for a specific stream.
        
        Args:
            name: Name of the stream
            seed: New seed value
        """
        stream = self.get(name)
        stream.set_seed(seed)
        self._seeds[name] = seed
    
    def set_all_seeds(self, base_seed: int) -> None:
        """
        Set seeds for all streams based on a base seed.
        
        Each stream gets a deterministic seed derived from the base.
        This ensures reproducibility across all streams.
        
        Args:
            base_seed: Base seed to derive individual seeds
        """
        # Use base_seed to generate unique seeds for each stream
        seed_gen = random.Random(base_seed)
        
        for name in sorted(self._streams.keys()):  # Sort for determinism
            derived_seed = seed_gen.randint(0, 2**31 - 1)
            self.set_seed(name, derived_seed)
        
        logger.debug(f"Set all seeds from base_seed={base_seed}")
    
    def reset(self, name: str) -> None:
        """
        Reset a specific stream to its initial seed.
        
        Args:
            name: Name of the stream
        """
        stream = self.get(name)
        stream.reset()
    
    def reset_all(self) -> None:
        """
        Reset all streams to their initial seeds.
        
        Useful for starting a new replication with the same random sequences.
        """
        for name, stream in self._streams.items():
            stream.reset()
        logger.debug("Reset all streams")
    
    def all_streams(self) -> List[str]:
        """Return names of all streams."""
        return list(self._streams.keys())
    
    def clear(self) -> None:
        """Remove all streams."""
        self._streams.clear()
        self._seeds.clear()
        logger.debug("Cleared RandomRegistry")
    
    def __contains__(self, name: str) -> bool:
        """Check if stream exists: 'arrivals' in registry"""
        return name in self._streams
    
    def __len__(self) -> int:
        """Number of streams."""
        return len(self._streams)


# ============================================================================
# Default Global Registry (convenience)
# ============================================================================

_default_registry: Optional[RandomRegistry] = None


def get_default_registry() -> RandomRegistry:
    """
    Get or create the default global registry.
    
    Provides a convenient singleton for simple use cases.
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = RandomRegistry()
    return _default_registry


def reset_default_registry() -> None:
    """Reset the default global registry."""
    global _default_registry
    _default_registry = None
