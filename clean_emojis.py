# -*- coding: utf-8 -*-
import os
import re

def remove_emojis_from_string(text):
    # Regex for typical emojis, keep ascii, standard punctuation, and simple latin
    # This keeps characters in the range of standard printable ASCII and a few extensions.
    return re.sub(r'[^\x00-\x7F]', '', text)

def strip_emojis(directory):
    for root, _, files in os.walk(directory):
        if 'env' in root or '.git' in root or '__pycache__' in root or 'runs' in root or 'Merged-Dataset' in root:
            continue
        for file in files:
            if file.endswith(('.py', '.html', '.js', '.css', '.md', '.txt')):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    cleaned = remove_emojis_from_string(content)
                    
                    if content != cleaned:
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(cleaned)
                        print(f"Cleaned emojis from {filepath}")
                except Exception as e:
                    print(f"Failed on {filepath}: {e}")

if __name__ == '__main__':
    strip_emojis('.')
