#!/usr/bin/env python3
import sys
import struct
import urllib.request
import os
import zlib

def get(url, start, end):
    req = urllib.request.Request(url)
    req.add_header('Range', f'bytes={start}-{end}')
    with urllib.request.urlopen(req) as r:
        return r.read()

def get_size(url):
    req = urllib.request.Request(url, method='HEAD')
    with urllib.request.urlopen(req) as r:
        return int(r.headers['Content-Length'])

def find_eocd(url, size):
    chunk = get(url, max(0, size - 65536), size - 1)
    idx = chunk.rfind(b'PK\x05\x06')
    if idx == -1:
        raise Exception("EOCD not found")
    eocd = chunk[idx:]
    cd_size, cd_offset = struct.unpack('<IQ' if len(eocd) > 20 and eocd[20:24] == b'PK\x06\x07' else '<II', eocd[12:20] if len(eocd) > 20 else eocd[12:20])
    return cd_offset, cd_size

def parse_cd(data):
    entries = {}
    pos = 0
    while pos < len(data):
        if data[pos:pos+4] != b'PK\x01\x02':
            break
        flag, method, _, _, crc, comp_size, uncomp_size, name_len, extra_len, comment_len = struct.unpack('<HHHHIIIHHHHHII', data[pos+6:pos+42])
        offset = struct.unpack('<I', data[pos+42:pos+46])[0]
        name = data[pos+46:pos+46+name_len].decode('utf-8', errors='ignore')
        entries[name] = (offset, comp_size, uncomp_size, method, crc)
        pos += 46 + name_len + extra_len + comment_len
    return entries

def download_file(url, entry, outpath):
    offset, comp_size, uncomp_size, method, crc = entry
    local_header = get(url, offset, offset + 29)
    name_len, extra_len = struct.unpack('<HH', local_header[26:30])
    data_offset = offset + 30 + name_len + extra_len
    compressed = get(url, data_offset, data_offset + comp_size - 1)
    
    if method == 0:
        data = compressed
    elif method == 8:
        data = zlib.decompress(compressed, -15)
    else:
        raise Exception(f"Unsupported compression method: {method}")
    
    os.makedirs(os.path.dirname(outpath) or '.', exist_ok=True)
    with open(outpath, 'wb') as f:
        f.write(data)

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <url> <path1> <path2> ...")
        sys.exit(1)
    
    url = sys.argv[1]
    patterns = sys.argv[2:]
    
    output_dir = os.path.basename(url).replace('.zip', '')
    os.makedirs(output_dir, exist_ok=True)
    
    size = get_size(url)
    cd_offset, cd_size = find_eocd(url, size)
    cd_data = get(url, cd_offset, cd_offset + cd_size - 1)
    entries = parse_cd(cd_data)
    
    for name, entry in entries.items():
        for pattern in patterns:
            if name.startswith(pattern) or name == pattern:
                print(f"Downloading: {name}")
                outpath = os.path.join(output_dir, name)
                download_file(url, entry, outpath)
                break
