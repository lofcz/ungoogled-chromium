import os

def add_patterns_to_file():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, 'update_lists.py')

    # extra patterns
    new_patterns = [
        '*.tflite',
        '*.binarypb', 
        '*.pb',
        '*.pbtxt.gz',
        '*.bin' # todo: scope down
    ]
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    start_idx = content.find('PRUNING_EXCLUDE_PATTERNS = [')
    if start_idx == -1:
        print("PRUNING_EXCLUDE_PATTERNS nenalezeno v souboru")
        return
    
    end_idx = content.find(']', start_idx)
    if end_idx == -1:
        print("Failed to locate end of PRUNING_EXCLUDE_PATTERNS")
        return
        
    current_list = content[start_idx:end_idx+1]
    
    # add extra patterns
    patterns_to_add = []
    for pattern in new_patterns:
        if f"'{pattern}'" not in current_list:
            patterns_to_add.append(f"    '{pattern}',\n")
    
    if patterns_to_add:
        new_content = (
            content[:end_idx] + 
            ''.join(patterns_to_add) +
            content[end_idx:]
        )
        
        with open(file_path, 'w') as f:
            f.write(new_content)
        print("update_lists.py patched")
    else:
        print("no patch applied - file already patched")

if __name__ == "__main__":
    add_patterns_to_file()
