import json
import argparse

def print_tree(node, prefix='/'):
    if isinstance(node, dict):
        for k, v in node.items():
            print(f"{prefix}{k}/")
            print_tree(v, prefix + k + '/')
    elif isinstance(node, list):
        for i, item in enumerate(node):
            print(f"{prefix}[{i}]/")
            print_tree(item, prefix)

def parse_json_file(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
        print_tree(data)

def main():
    parser = argparse.ArgumentParser(description='Process a JSON file.')
    parser.add_argument('json_file_path', type=str, help='The path to the JSON file to process.')

    args = parser.parse_args()

    parse_json_file(args.json_file_path)

if __name__ == "__main__":
    main()