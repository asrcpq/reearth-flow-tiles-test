#!/usr/bin/env python3

import subprocess
import sys

def run_git(cmd):
	result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
	return result.stdout.strip()

def main():
	days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
	current_user = run_git("git config user.email")
	
	output = run_git("git fetch")
	output = run_git(
		f"git log --all --source --since='{days} days ago' "
		f"--author='^((?!{current_user}).)*$' --perl-regexp "
		f"--format='%cI %S' --name-only"
	)
	
	file_info = {}
	current_date = None
	current_branch = None
	
	for line in output.split('\n'):
		if not line:
			continue
		parts = line.split()
		if len(parts) == 2 and '-' in parts[0]:  # Date line
			current_date = parts[0]
			current_branch = parts[1].replace('refs/remotes/origin/', '')
		elif current_date:	# File line
			key = f"{line}|{current_branch}"
			if key not in file_info:
				file_info[key] = current_date
	
	out = []
	for key in sorted(file_info.keys()):
		file, branch = key.split('|')
		date = file_info[key]
		out.append((date, branch, file))
	out.sort()
	for date, branch, file in out:
		print(date, branch, file)

if __name__ == "__main__":
	main()
