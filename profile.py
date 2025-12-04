#!/usr/bin/env python3
import subprocess, sys, os, time, signal
if os.geteuid() != 0:
    print("Error: needs sudo")
    sys.exit(1)
cmd = sys.argv[1] if len(sys.argv) > 1 else sys.exit("Usage: sudo python profile.py <command>")
duration = int(sys.argv[2]) if len(sys.argv) > 2 else 30
flamegraph_path = '/Users/tsq/Projects/FlameGraph/flamegraph.pl'
target = subprocess.Popen(cmd, shell=True)
time.sleep(0.5)
pid = target.pid
dtrace = subprocess.Popen(["dtrace", "-x", "ustackframes=100", "-n", f'profile-4999 /pid == {pid}/ {{ @[ustack(50)] = count(); }}'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
print(f"Profiling PID {pid} for {duration}s...")
try:
    time.sleep(duration)
except KeyboardInterrupt:
    pass
dtrace.send_signal(signal.SIGINT)
stdout, stderr = dtrace.communicate()
target.terminate()
target.wait()
stacks = {}
current_stack = []
for line in stdout.split('\n'):
    line = line.strip()
    if not line or line.startswith('dtrace'):
        continue
    if line.isdigit():
        if current_stack:
            stack_key = ';'.join(reversed(current_stack))
            stacks[stack_key] = stacks.get(stack_key, 0) + int(line)
            current_stack = []
    elif '`' in line:
        func = line.split('`')[-1].split('+')[0].split('(')[0]
        current_stack.append(func)
collapsed = '\n'.join(f"{stack} {count}" for stack, count in stacks.items())
subprocess.run([flamegraph_path], input=collapsed, text=True, stdout=open('flamegraph.svg', 'w'))
subprocess.run(['open', 'flamegraph.svg'])
