# ChatGPT generated. It has a bug w.r.t to contact photo extract, but overall it works

import sys
import base64
import argparse
import os

def main():
    parser = argparse.ArgumentParser(description='Parse VCF contact files and extract individual contacts')
    parser.add_argument('vcf_file', help='VCF file to parse')
    parser.add_argument('-o', '--output-dir', default='.', help='Output directory for individual VCF files (default: current directory)')
    
    args = parser.parse_args()
    
    # Open the VCF file
    try:
        vcf_file = open(args.vcf_file, 'r')
    except Exception as e:
        print(f"Error: Could not open file '{args.vcf_file}': {e}")
        sys.exit(1)
    
    # Create output directory if it doesn't exist
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)

    # Parse the VCF file
    contacts = []
    current_contact = {}
    in_photo = False
    photo_data = ''
    for line in vcf_file:
        line = line.strip()
        if line.startswith('BEGIN:VCARD'):
            current_contact = {}
        elif line.startswith('END:VCARD'):
            if in_photo:
                current_contact['PHOTO;ENCODING=BASE64'] = photo_data
                photo_data = ''
            contacts.append(current_contact)
            current_contact = {}
            in_photo = False
        elif line.startswith('PHOTO;'):
            in_photo = True
        elif line == 'END:PHOTO':
            in_photo = False
        elif in_photo:
            photo_data += line
        elif not in_photo:
            parts = line.split(':')
            if len(parts) == 2:
                current_contact[parts[0]] = parts[1]

    # Close the VCF file
    vcf_file.close()

    # Create individual VCF files for each contact
    serial_number = 1
    for contact in contacts:
        # Get the contact name
        if 'FN' in contact:
            name = contact['FN']
        else:
            name = 'Unknown ' + str(serial_number)
            serial_number += 1
        
        # Create a new VCF file for the contact
        vcf_path = os.path.join(args.output_dir, name + '.vcf')
        vcf_out = open(vcf_path, 'w')
        
        # Write the contact information to the VCF file
        vcf_out.write('BEGIN:VCARD\n')
        for key, value in contact.items():
            if key != 'PHOTO;ENCODING=BASE64':
                vcf_out.write(key + ': ' + value + '\n')
        vcf_out.write('END:VCARD\n')
        
        # Close the VCF file
        vcf_out.close()
        
        # Decode and write the photo data to disk
        if 'PHOTO;ENCODING=BASE64' in contact:
            photo_data = contact['PHOTO;ENCODING=BASE64']
            photo_data = photo_data.encode('utf-8')
            photo_data = base64.decodebytes(photo_data)
            photo_path = os.path.join(args.output_dir, name + '.jpeg')
            photo_out = open(photo_path, 'wb')
            photo_out.write(photo_data)
            photo_out.close()

if __name__ == '__main__':
    main()