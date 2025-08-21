from setuptools import setup, find_packages

setup(
    name='useful_scripts',
    version='0.1.0',
    packages=find_packages(),
   install_requires=[
        'markdown2',
        'Pillow',
    ],
    entry_points={
        'console_scripts': [
            'ApplyDiff = ApplyDiff:main',
            'asm_emit = asm_emit:main',
            'html_entities = html_entities:main',
            'pyast = pyast:main',
            'mdcomdec = mdcomdec:main',
            'parse_vcf = parse_vcf:main',
            'jsontree = jsontree:main',            
            'markdown_render = markdown_render:main',
            'src_to_llm_context = src_to_llm_context:main',
            'qslideshow = qslideshow:main',
            #'preprocess = preprocess:main',
        ],
    }
)
