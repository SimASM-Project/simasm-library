"""
config/file_config.py

Centralized file path configuration for SimASM.
"""

import os

# Project root is one level up from config/
PROJECT_ROOT = os.path.dirname(os.path.abspath(os.path.join(__file__, '../')))


class FileConfig:
    """
    Central configuration for all file paths in SimASM.
    
    Usage:
        from simasm.config.file_config import FileConfig
        
        log_file = os.path.join(FileConfig.log_path, 'run.log')
    """
    
    # Root path
    root_path = PROJECT_ROOT
    
    # Main package paths
    config_path = os.path.join(PROJECT_ROOT, 'config')
    core_path = os.path.join(PROJECT_ROOT, 'core')
    experimenter_path = os.path.join(PROJECT_ROOT, 'experimenter')
    jupyter_path = os.path.join(PROJECT_ROOT, 'jupyter')
    log_path = os.path.join(PROJECT_ROOT, 'log')
    parser_path = os.path.join(PROJECT_ROOT, 'parser')
    runtime_path = os.path.join(PROJECT_ROOT, 'runtime')
    verification_path = os.path.join(PROJECT_ROOT, 'verification')
    
    # I/O paths
    input_path = os.path.join(PROJECT_ROOT, 'input')
    output_path = os.path.join(PROJECT_ROOT, 'output')
    
    # Test paths (outside main package)
    test_path = os.path.join(os.path.dirname(PROJECT_ROOT), 'test')
    test_input_path = os.path.join(test_path, 'input')
    test_output_path = os.path.join(test_path, 'output')
    test_log_path = os.path.join(test_path, 'log')
    
    @classmethod
    def ensure_directories(cls) -> None:
        """Create all directories if they don't exist."""
        directories = [
            cls.log_path,
            cls.input_path,
            cls.output_path,
            cls.test_path,
            cls.test_input_path,
            cls.test_output_path,
            cls.test_log_path,
        ]
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
