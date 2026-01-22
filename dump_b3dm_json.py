#!/usr/bin/env python3
"""
Extract metadata from B3DM (Batched 3D Model) tileset files.
Usage: python extract_b3dm_metadata.py <file.b3dm>
"""

import sys
import struct
import json


def read_b3dm_metadata(filepath):
    """Extract and display metadata from a B3DM file."""
    
    with open(filepath, 'rb') as f:
        # Read header (28 bytes)
        header_data = f.read(28)
        
        if len(header_data) < 28:
            print("Error: File too small to be a valid B3DM file")
            return
        
        # Parse header
        magic = header_data[0:4].decode('ascii')
        version = struct.unpack('<I', header_data[4:8])[0]
        byte_length = struct.unpack('<I', header_data[8:12])[0]
        feature_table_json_byte_length = struct.unpack('<I', header_data[12:16])[0]
        feature_table_binary_byte_length = struct.unpack('<I', header_data[16:20])[0]
        batch_table_json_byte_length = struct.unpack('<I', header_data[20:24])[0]
        batch_table_binary_byte_length = struct.unpack('<I', header_data[24:28])[0]
        
        # Validate magic number
        if magic != 'b3dm':
            print(f"Error: Invalid magic number '{magic}'. Expected 'b3dm'")
            return
        
        # Display header information
        print("=" * 60)
        print("B3DM HEADER INFORMATION")
        print("=" * 60)
        print(f"Magic:                              {magic}")
        print(f"Version:                            {version}")
        print(f"Byte Length:                        {byte_length:,} bytes")
        print(f"Feature Table JSON Byte Length:     {feature_table_json_byte_length:,} bytes")
        print(f"Feature Table Binary Byte Length:   {feature_table_binary_byte_length:,} bytes")
        print(f"Batch Table JSON Byte Length:       {batch_table_json_byte_length:,} bytes")
        print(f"Batch Table Binary Byte Length:     {batch_table_binary_byte_length:,} bytes")
        
        # Calculate glTF payload size
        gltf_byte_length = (byte_length - 28 - 
                           feature_table_json_byte_length - 
                           feature_table_binary_byte_length -
                           batch_table_json_byte_length - 
                           batch_table_binary_byte_length)
        print(f"glTF Payload Byte Length:           {gltf_byte_length:,} bytes")
        
        # Read Feature Table JSON
        print("\n" + "=" * 60)
        print("FEATURE TABLE JSON")
        print("=" * 60)
        if feature_table_json_byte_length > 0:
            feature_table_json_data = f.read(feature_table_json_byte_length)
            # Remove padding (trailing whitespace/null bytes)
            feature_table_json_str = feature_table_json_data.rstrip(b'\x00\x20').decode('utf-8')
            try:
                feature_table = json.loads(feature_table_json_str)
                print(json.dumps(feature_table, indent=2))
            except json.JSONDecodeError as e:
                print(f"Error parsing Feature Table JSON: {e}")
                print(f"Raw data: {feature_table_json_str[:200]}")
        else:
            print("(empty)")
        
        # Skip Feature Table Binary
        if feature_table_binary_byte_length > 0:
            f.read(feature_table_binary_byte_length)
            print(f"\nFeature Table Binary: {feature_table_binary_byte_length:,} bytes (skipped)")
        
        # Read Batch Table JSON
        print("\n" + "=" * 60)
        print("BATCH TABLE JSON")
        print("=" * 60)
        if batch_table_json_byte_length > 0:
            batch_table_json_data = f.read(batch_table_json_byte_length)
            # Remove padding
            batch_table_json_str = batch_table_json_data.rstrip(b'\x00\x20').decode('utf-8')
            try:
                batch_table = json.loads(batch_table_json_str)
                print(json.dumps(batch_table, indent=2))
                
                # Display batch table statistics
                if isinstance(batch_table, dict):
                    print(f"\nBatch Table Properties: {len(batch_table)} property/properties")
                    for key, value in batch_table.items():
                        if isinstance(value, list):
                            print(f"  - {key}: {len(value)} values")
                        else:
                            print(f"  - {key}: {type(value).__name__}")
            except json.JSONDecodeError as e:
                print(f"Error parsing Batch Table JSON: {e}")
                print(f"Raw data: {batch_table_json_str[:200]}")
        else:
            print("(empty)")
        
        # Skip Batch Table Binary
        if batch_table_binary_byte_length > 0:
            print(f"\nBatch Table Binary: {batch_table_binary_byte_length:,} bytes (skipped)")
        
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"File:           {filepath}")
        print(f"Format:         B3DM v{version}")
        print(f"Total Size:     {byte_length:,} bytes")
        print(f"glTF Model:     {gltf_byte_length:,} bytes ({gltf_byte_length/byte_length*100:.1f}%)")
        print("=" * 60)


def main():
    if len(sys.argv) != 2:
        print("Usage: python extract_b3dm_metadata.py <file.b3dm>")
        sys.exit(1)
    
    filepath = sys.argv[1]
    
    try:
        read_b3dm_metadata(filepath)
    except FileNotFoundError:
        print(f"Error: File '{filepath}' not found")
        sys.exit(1)
    except Exception as e:
        print(f"Error processing file: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
