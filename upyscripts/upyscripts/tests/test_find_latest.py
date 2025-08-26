import os
from useful_libs.files.find import find_latest_file_date

def main():
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    latest_date, latest_file = find_latest_file_date(path, '*.py')
    
    if latest_date:
        print(f'The latest Python file is: {latest_file} ({latest_date})')
    else:
        print('No Python files found in the specified folder.')


if __name__ == "__main__":
    main()        