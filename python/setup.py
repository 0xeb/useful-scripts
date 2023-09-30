from setuptools import setup, find_packages

setup(
    name='useful_scripts',
    version='0.1.0',
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'ApplyDiff = ApplyDiff:main',
            'asm_emit = asm_emit:main',
            'html_entities = html_entities:main',
            'mdcomdec = mdcomdec:main',
            'parse_vcf = parse_vcf:main',
            #'preprocess = preprocess:main',
        ],
    }
)
