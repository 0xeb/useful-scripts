# test_mdparser.py
from useful_libs.mdparser import parse_markdown

test_string = """
# Meta

## Socials

This is a test social link

## YouTube

### URL

https://youtu.be/NQFn-hmmeLQ

### Title

Some title goes here

### Description

Some description goes here...

"""
def main():
    headings, d = parse_markdown(test_string)

    print(d['Meta']['YouTube']['Title'])
    print(d['Meta']['YouTube']['URL'])

if __name__ == "__main__":
    main()
