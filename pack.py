import os

dirs_to_pack = ['agents', 'api', 'context_engine', 'core', 'graph', 'worker', 'scripts']
files_to_pack = ['main.py', 'README.md', 'pyproject.toml', 'test_request.py', 'check_db.py']
output_file = 'gemini.md'

with open(output_file, 'w', encoding='utf-8') as outfile:
    outfile.write("# Project Overview\n\nThis file contains the complete source code and necessary context for the project.\n\n")
    
    # include tree but ignore .venv, .git, chroma_db
    try:
        import subprocess
        # Get simplified tree using powershell if tree /f is too messy or use os.walk
        tree_out = []
        for d in ['.'] + dirs_to_pack:
            if d == '.':
                for f in files_to_pack:
                    tree_out.append(f)
            else:
                for root, dirs, files in os.walk(d):
                    for file in files:
                        if file.endswith('.py') or file.endswith('.md') or file.endswith('.toml'):
                            filepath = os.path.join(root, file).replace('\\', '/')
                            tree_out.append(filepath)
        outfile.write("## Directory Structure\n```\n" + "\n".join(sorted(tree_out)) + "\n```\n\n")
    except Exception as e:
        pass
        
    for file in files_to_pack:
        if os.path.exists(file):
            ext = file.split('.')[-1]
            lang = 'python' if ext == 'py' else 'markdown' if ext == 'md' else 'toml' if ext == 'toml' else ''
            outfile.write(f"## `/{file}`\n```{lang}\n")
            with open(file, 'r', encoding='utf-8') as infile:
                outfile.write(infile.read())
            outfile.write("\n```\n\n")
            
    for directory in dirs_to_pack:
        for root, dirs, files in os.walk(directory):
            # skipping __pycache__
            if '__pycache__' in root:
                continue
            for file in files:
                if file.endswith(('.py', '.json', '.md', '.toml', '.ts', '.tsx')):
                    filepath = os.path.join(root, file)
                    filepath_posix = filepath.replace('\\', '/')
                    ext = filepath.split('.')[-1]
                    lang = 'python' if ext in ['py'] else 'json' if ext == 'json' else 'markdown' if ext == 'md' else 'typescript' if ext in ['ts', 'tsx'] else ''
                    outfile.write(f"## `/{filepath_posix}`\n```{lang}\n")
                    try:
                        with open(filepath, 'r', encoding='utf-8') as infile:
                            outfile.write(infile.read())
                    except Exception as e:
                        outfile.write(f"# Error reading: {e}")
                    outfile.write("\n```\n\n")
