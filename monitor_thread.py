#!/usr/bin/env python3
import subprocess
import sys

def monitor_threads(pid):
    dtrace_script = f'proc:::lwp-create /pid == {pid}/ {{ printf("Thread created: TID=%d\\n", args[0]->pr_lwpid); }}'
    
    try:
        process = subprocess.Popen(
            ['sudo', 'dtrace', '-n', dtrace_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        for line in iter(process.stdout.readline, ''):
            if line.strip():
                print(line.strip())
        
    except KeyboardInterrupt:
        process.terminate()
        process.wait()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python thread_monitor.py <command> [args...]")
        sys.exit(1)
    
    cmd = sys.argv[1:]
    proc = subprocess.Popen(cmd)
    
    try:
        monitor_threads(proc.pid)
    finally:
        proc.terminate()
        proc.wait()
