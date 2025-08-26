#!/usr/bin/env python3
"""
PDF Image Converter
A tool to extract images from PDFs or compile images into PDFs
"""

import os
import sys
import fitz  # PyMuPDF
from pathlib import Path
import argparse
import hashlib
from PIL import Image
import io

# Supported image formats
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp'}

def extract_images_from_pdf(pdf_path, output_dir):
    """
    Extract all unique images from a PDF file and save them to the specified directory.
    
    Args:
        pdf_path: Path to the PDF file
        output_dir: Directory where images will be saved
    
    Returns:
        Number of unique images extracted
    """
    # Open the PDF
    pdf_document = fitz.open(pdf_path)
    
    # Dictionary to track unique images by their xref or content hash
    extracted_images = {}  # xref -> (image_data, extension)
    image_hashes = set()  # To track unique content
    
    print(f"  Scanning {len(pdf_document)} pages for unique images...")
    
    # First pass: collect all unique images
    for page_num in range(len(pdf_document)):
        page = pdf_document[page_num]
        
        # Get list of images on the page
        image_list = page.get_images(full=True)
        
        for img in image_list:
            # Get the image XREF (unique identifier within the PDF)
            xref = img[0]
            
            # Skip if we've already processed this xref
            if xref in extracted_images:
                continue
            
            try:
                # Extract image data
                base_image = pdf_document.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                # Calculate hash to detect truly duplicate content
                image_hash = hashlib.md5(image_bytes).hexdigest()
                
                # Skip if we've seen this exact image content before
                if image_hash in image_hashes:
                    print(f"    Skipping duplicate image (xref {xref})")
                    continue
                
                # Store the unique image
                extracted_images[xref] = (image_bytes, image_ext, page_num + 1)
                image_hashes.add(image_hash)
                
            except Exception as e:
                print(f"    Warning: Could not extract image xref {xref}: {e}")
                continue
    
    # Second pass: save all unique images
    image_count = 0
    for xref, (image_bytes, image_ext, first_page) in extracted_images.items():
        image_count += 1
        
        # Generate filename with simple numbering
        image_filename = f"image_{image_count:03d}_page{first_page}.{image_ext}"
        image_path = os.path.join(output_dir, image_filename)
        
        # Save the image
        with open(image_path, "wb") as image_file:
            image_file.write(image_bytes)
        
        print(f"  Extracted: {image_filename}")
    
    pdf_document.close()
    return image_count

def compile_images_to_pdf(input_paths, output_pdf_path, img_per_page=1, quality=95, fit_page=True, maintain_aspect=True, recursive=False):
    """
    Compile images into a PDF file.
    
    Args:
        input_paths: List of image file paths or directory containing images
        output_pdf_path: Path for the output PDF file
        img_per_page: Number of images per page (1, 2, 4, or 6)
        quality: JPEG quality for compression (1-100)
        fit_page: Whether to fit images to page size
        maintain_aspect: Whether to maintain aspect ratio
        recursive: Whether to search directories recursively
    
    Returns:
        Number of images compiled
    """
    # Collect all image files
    image_files = []
    
    for input_path in input_paths:
        path = Path(input_path)
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            image_files.append(path)
        elif path.is_dir():
            # Get all images from directory, sorted by name
            if recursive:
                dir_images = [f for f in path.rglob('*') 
                             if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS]
            else:
                dir_images = [f for f in path.iterdir() 
                             if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS]
            image_files.extend(sorted(dir_images))
    
    if not image_files:
        print("No image files found to compile")
        return 0
    
    print(f"\nCompiling {len(image_files)} images into PDF...")
    
    # Create PDF document
    pdf_document = fitz.open()
    
    # Page size (A4 by default)
    page_width, page_height = fitz.paper_size("A4")
    
    # Calculate layout based on images per page
    layouts = {
        1: [(0, 0, page_width, page_height)],
        2: [(0, 0, page_width, page_height/2),
            (0, page_height/2, page_width, page_height)],
        4: [(0, 0, page_width/2, page_height/2),
            (page_width/2, 0, page_width, page_height/2),
            (0, page_height/2, page_width/2, page_height),
            (page_width/2, page_height/2, page_width, page_height)],
        6: [(0, 0, page_width/2, page_height/3),
            (page_width/2, 0, page_width, page_height/3),
            (0, page_height/3, page_width/2, 2*page_height/3),
            (page_width/2, page_height/3, page_width, 2*page_height/3),
            (0, 2*page_height/3, page_width/2, page_height),
            (page_width/2, 2*page_height/3, page_width, page_height)]
    }
    
    if img_per_page not in layouts:
        print(f"Warning: {img_per_page} images per page not supported. Using 1.")
        img_per_page = 1
    
    layout = layouts[img_per_page]
    images_added = 0
    
    for i in range(0, len(image_files), img_per_page):
        # Create a new page
        page = pdf_document.new_page(width=page_width, height=page_height)
        
        # Add images to this page
        for j in range(img_per_page):
            if i + j >= len(image_files):
                break
            
            image_path = image_files[i + j]
            print(f"  Adding: {image_path.name}")
            
            try:
                # Get the rectangle for this image position
                rect = fitz.Rect(layout[j])
                
                # Open and process the image
                with Image.open(image_path) as pil_img:
                    # Convert RGBA to RGB if necessary
                    if pil_img.mode in ('RGBA', 'LA', 'P'):
                        rgb_img = Image.new('RGB', pil_img.size, (255, 255, 255))
                        rgb_img.paste(pil_img, mask=pil_img.split()[-1] if pil_img.mode == 'RGBA' else None)
                        pil_img = rgb_img
                    elif pil_img.mode != 'RGB':
                        pil_img = pil_img.convert('RGB')
                    
                    # Save to bytes
                    img_bytes = io.BytesIO()
                    pil_img.save(img_bytes, format='JPEG', quality=quality)
                    img_bytes.seek(0)
                    
                    # Insert image into PDF
                    if fit_page:
                        # Fit image to the rectangle while maintaining aspect ratio if requested
                        if maintain_aspect:
                            # Calculate scaling to fit within rectangle
                            img_aspect = pil_img.width / pil_img.height
                            rect_aspect = rect.width / rect.height
                            
                            if img_aspect > rect_aspect:
                                # Image is wider - fit width
                                new_width = rect.width
                                new_height = rect.width / img_aspect
                                y_offset = (rect.height - new_height) / 2
                                rect = fitz.Rect(rect.x0, rect.y0 + y_offset, 
                                               rect.x1, rect.y0 + y_offset + new_height)
                            else:
                                # Image is taller - fit height
                                new_height = rect.height
                                new_width = rect.height * img_aspect
                                x_offset = (rect.width - new_width) / 2
                                rect = fitz.Rect(rect.x0 + x_offset, rect.y0,
                                               rect.x0 + x_offset + new_width, rect.y1)
                    
                    page.insert_image(rect, stream=img_bytes.getvalue())
                    images_added += 1
                    
            except Exception as e:
                print(f"    Warning: Could not add {image_path.name}: {e}")
    
    # Save the PDF
    pdf_document.save(output_pdf_path, deflate=True, garbage=3)
    pdf_document.close()
    
    return images_added

def process_extraction(input_path, output_base_dir=None, recursive=False):
    """
    Process PDF files for extraction - either a single file or all PDFs in a directory.
    
    Args:
        input_path: Path to PDF file or directory
        output_base_dir: Optional output directory
        recursive: Whether to process subdirectories recursively
    """
    input_path = Path(input_path)
    
    # Determine if input is a file or directory
    if input_path.is_file() and input_path.suffix.lower() == '.pdf':
        pdf_files = [input_path]
        base_dir = input_path.parent
    elif input_path.is_dir():
        if recursive:
            pdf_files = list(input_path.rglob('*.pdf')) + list(input_path.rglob('*.PDF'))
        else:
            pdf_files = list(input_path.glob('*.pdf')) + list(input_path.glob('*.PDF'))
        base_dir = input_path
    else:
        print(f"Error: {input_path} is not a valid PDF file or directory")
        return
    
    if not pdf_files:
        print("No PDF files found to process")
        return
    
    # Set output base directory
    if output_base_dir:
        output_base = Path(output_base_dir)
        output_base.mkdir(parents=True, exist_ok=True)
    else:
        output_base = base_dir
    
    total_images = 0
    processed_pdfs = 0
    
    print(f"\nExtracting images from {len(pdf_files)} PDF file(s)...\n")
    
    for pdf_path in pdf_files:
        print(f"Processing: {pdf_path.name}")
        
        # Create output folder named after the PDF (without extension)
        folder_name = pdf_path.stem
        output_dir = output_base / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Extract images
            image_count = extract_images_from_pdf(str(pdf_path), str(output_dir))
            
            if image_count > 0:
                print(f"  ✓ Extracted {image_count} unique image(s) to {output_dir}\n")
                total_images += image_count
                processed_pdfs += 1
            else:
                print(f"  ⚠ No images found in this PDF\n")
                # Remove empty folder
                try:
                    output_dir.rmdir()
                except:
                    pass
                    
        except Exception as e:
            print(f"  ✗ Error processing {pdf_path.name}: {str(e)}\n")
    
    # Summary
    print("=" * 50)
    print(f"Extraction complete!")
    print(f"  • Processed PDFs: {processed_pdfs}/{len(pdf_files)}")
    print(f"  • Total unique images extracted: {total_images}")
    print(f"  • Output location: {output_base}")

def main():
    parser = argparse.ArgumentParser(
        description='A PDF-Image converter: Extract images from PDFs or compile images into PDFs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXTRACTION Examples:
  %(prog)s extract ~/Documents/myfile.pdf
      Extract images from a single PDF
  
  %(prog)s extract ~/Documents/PDFs/
      Extract images from all PDFs in the directory
  
  %(prog)s extract ~/Documents/PDFs/ -o ~/Desktop/ExtractedImages/
      Extract to a custom output directory
  
  %(prog)s extract ~/Documents/PDFs/ -r
      Recursively extract images from PDFs in all subdirectories

COMPILATION Examples:
  %(prog)s compile ~/Pictures/vacation/ -o ~/Documents/vacation.pdf
      Compile all images from a folder into a PDF
  
  %(prog)s compile ~/Pictures/*.jpg -o ~/Documents/photos.pdf
      Compile specific images into a PDF
  
  %(prog)s compile ~/Pictures/ -o ~/Documents/album.pdf --images-per-page 4
      Create a PDF with 4 images per page (photo album style)
  
  %(prog)s compile ~/Pictures/ -o ~/Documents/compressed.pdf --quality 60
      Create a compressed PDF with lower quality images
  
  %(prog)s compile ~/Pictures/ -o ~/Documents/all_images.pdf -r
      Recursively compile all images from subdirectories into a PDF
        """
    )
    
    subparsers = parser.add_subparsers(dest='mode', help='Operation mode')
    
    # Extract subcommand
    extract_parser = subparsers.add_parser('extract', help='Extract images from PDF(s)')
    extract_parser.add_argument(
        'input',
        help='Path to a PDF file or directory containing PDFs'
    )
    extract_parser.add_argument(
        '-o', '--output',
        help='Output base directory (default: same as input)',
        default=None
    )
    extract_parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        help='Recursively process PDFs in subdirectories'
    )
    
    # Compile subcommand
    compile_parser = subparsers.add_parser('compile', help='Compile images into a PDF')
    compile_parser.add_argument(
        'input',
        nargs='+',
        help='Path(s) to image files or directories containing images'
    )
    compile_parser.add_argument(
        '-o', '--output',
        required=True,
        help='Output PDF file path'
    )
    compile_parser.add_argument(
        '--images-per-page',
        type=int,
        choices=[1, 2, 4, 6],
        default=1,
        help='Number of images per page (default: 1)'
    )
    compile_parser.add_argument(
        '--quality',
        type=int,
        default=95,
        help='JPEG compression quality 1-100 (default: 95)'
    )
    compile_parser.add_argument(
        '--no-fit',
        action='store_true',
        help='Do not fit images to page size'
    )
    compile_parser.add_argument(
        '--no-aspect',
        action='store_true',
        help='Do not maintain aspect ratio when fitting'
    )
    compile_parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        help='Recursively search directories for images'
    )
    
    args = parser.parse_args()
    
    if not args.mode:
        parser.print_help()
        sys.exit(1)
    
    # Check if required libraries are installed
    try:
        import fitz
    except ImportError:
        print("\nError: PyMuPDF is not installed.")
        print("Please install it using: pip3 install PyMuPDF")
        sys.exit(1)
    
    try:
        from PIL import Image
    except ImportError:
        print("\nError: Pillow is not installed.")
        print("Please install it using: pip3 install Pillow")
        sys.exit(1)
    
    if args.mode == 'extract':
        process_extraction(args.input, args.output, recursive=args.recursive)
    
    elif args.mode == 'compile':
        output_path = Path(args.output)
        
        # Ensure output has .pdf extension
        if output_path.suffix.lower() != '.pdf':
            output_path = output_path.with_suffix('.pdf')
        
        # Compile images
        image_count = compile_images_to_pdf(
            args.input,
            str(output_path),
            img_per_page=args.images_per_page,
            quality=args.quality,
            fit_page=not args.no_fit,
            maintain_aspect=not args.no_aspect,
            recursive=args.recursive
        )
        
        if image_count > 0:
            print(f"\n✓ Successfully compiled {image_count} images into {output_path}")
            print(f"  • Images per page: {args.images_per_page}")
            print(f"  • Quality: {args.quality}%")
            file_size = output_path.stat().st_size / (1024 * 1024)
            print(f"  • File size: {file_size:.2f} MB")
        else:
            print("\n✗ No images were compiled")

if __name__ == "__main__":
    main()
