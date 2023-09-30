"""
Markdown compose/decompose script

Decompose mode: Decompose a single Markdown file (by Heading1 marker) into multiple files
Compose mode: Use this script to compose lose Markdown files into a single file
"""

import os
import re
import argparse

def decompose_markdown(input_file, output_folder='.notes'):
    with open(input_file, 'r', encoding='utf-8') as md_file:
        content = md_file.read()

    if not os.path.exists(output_folder):
        try:
            os.makedirs(output_folder)
        except Exception as e:
            print(f"Failed to create output folder: {e}")
            return

    current_title = None
    current_file = None
    i = 0
    for line in content.split('\n'):
        heading_match = re.match(r'# (.+)', line)
        if heading_match:
            i += 1
            if current_file:
                current_file.close()
            current_title = heading_match.group(1)
            current_file = open(f'{output_folder}/#{i:03} - {current_title}.md', 'w', encoding='utf-8')
        elif current_file:
            current_file.write(line + '\n')

    if current_file:
        current_file.close()


def recompose_markdown(input_folder, output_file):
    files = sorted([f for f in os.listdir(input_folder) if f.endswith('.md')])

    with open(output_file, 'w', encoding='utf-8') as md_file:
        for file in files:
            file_path = os.path.join(input_folder, file)
            with open(file_path, 'r', encoding='utf-8') as file_content:
                title = file.split(' - ')[1].replace('.md', '')
                md_file.write(f'# {title}\n')
                md_file.write(file_content.read())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Unified tool for parsing and recomposing markdown files.')
    parser.add_argument('action', choices=['c', 'd'], help='c for compose, d for decompose')
    parser.add_argument('-i', '--input', required=True, help='The input file (for decompose) or folder (for compose).')
    parser.add_argument('-o', '--output', required=True, help='The output folder (for decompose) or file (for compose).')

    args = parser.parse_args()

    if args.action == 'd':
        decompose_markdown(args.input, args.output)
    elif args.action == 'c':
        recompose_markdown(args.input, args.output)
