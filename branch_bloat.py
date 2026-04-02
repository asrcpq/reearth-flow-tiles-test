import subprocess
import sys

def get_branch_size(branch_name):
    """
    Calculates the total size of all files in a branch (excluding .git)
    using git ls-tree. Size is returned in bytes.
    """
    try:
        # -r: recursive, -l: show object size, -z: null-terminated for safety
        cmd = ["git", "ls-tree", "-r", "-l", branch_name]
        result = subprocess.check_output(cmd, text=True)
        
        total_size = 0
        for line in result.splitlines():
            parts = line.split()
            # ls-tree format: <mode> <type> <sha> <size> <path>
            # We check if the object is a 'blob' (file)
            if parts[1] == "blob":
                size = int(parts[3])
                total_size += size
        return total_size
    except subprocess.CalledProcessError as e:
        print(f"Error accessing branch '{branch_name}': {e}")
        sys.exit(1)

def format_size(size_bytes):
    """Helper to make bytes human-readable."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} TB"

def main():
    branch_a = sys.argv[1]
    try:
        branch_b = sys.argv[2]
    except IndexError:
        branch_b = "HEAD"  # Default to current branch if not provided

    print(f"Analyzing {branch_a} vs {branch_b}...")

    size_a = get_branch_size(branch_a)
    size_b = get_branch_size(branch_b)
    diff = size_b - size_a

    print("-" * 30)
    print(f"{branch_a:15}: {format_size(size_a)}")
    print(f"{branch_b:15}: {format_size(size_b)}")
    print("-" * 30)
    
    prefix = "+" if diff > 0 else ""
    print(f"Estimated Bloat: {prefix}{format_size(diff)}")

if __name__ == "__main__":
    main()