import os
from typing import Iterator

EXCLUDED_DIRS = {
    ".git", "__pycache__", "node_modules", "venv", 
    ".venv", "build", "dist", "target"
}

MAX_FILE_SIZE = 500 * 1024  # 500 KB

def walk_repo(repo_path: str) -> Iterator[tuple[str, str]]:
    """Yields (absolute_file_path, source_text) for every .py and .java file."""
    repo_path = os.path.abspath(repo_path)
    
    for root, dirs, files in os.walk(repo_path):
        # Modify dirs in-place to skip excluded directories
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        
        for file in files:
            if not (file.endswith(".py") or file.endswith(".java")):
                continue
            
            file_path = os.path.join(root, file)
            
            try:
                if os.path.getsize(file_path) > MAX_FILE_SIZE:
                    continue
                
                with open(file_path, "r", encoding="utf-8") as f:
                    source_text = f.read()
                    
                yield (file_path, source_text)
            except Exception:
                # Silently skip files that we can't read or get size of
                pass
