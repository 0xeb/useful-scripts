"""
Apply a DIFF file to a binary file.


A DIFF file can be generated from IDA Pro for example or the output of "FC.EXE /B file1.bin file2.bin
"""
import os, sys, re, getopt

# TODO:
# -- make as an IDA plugin
# -- add "Apply DIF" menu
# -- refactor

#import code

def apply_diff(diff_file, bin_file, verify):
    # Get the binary file size
    try:
        bin_size = os.path.getsize(bin_file)
    except:
        return (False, f"Binary file '{bin_file}' not found!")

    # Open the binary file for updates
    try:
        bf = open(bin_file, 'r+b')
    except:
        return (False, f"Binary file '{bin_file}' could not be open for updates")

    # Compile the regular expression
    diff_re = re.compile(r'^([0-9a-f]+): ([0-9a-f]{2}) ([0-9a-f]{2})$', re.IGNORECASE)

    # Open the diff file
    try:
        df = open(diff_file, 'r')
    except:
        bf.close()
        return (False, f"Diff file '{diff_file}' could not be open for reading")

    # Read the diff file
    count = 0
    nwarning = 0
    try:
        for (line_no, line) in enumerate(df, start=1):
            m = diff_re.match(line.strip())
            if not m:
                continue

            seek_pos = int(m.group(1), 16)
            if seek_pos > bin_size:
                raise Exception(f"Seek position 0x{seek_pos:X} in diff file is greater than the file size!")

            if verify:
                bf.seek(seek_pos)
                v = ord(bf.read(1))
                o = int(m.group(2), 16)

                if v != o:
                    print(f"WARNING: verification failed. Original byte {o:02X} is expected, {v:02X} found instead. Skipping.")
                    nwarning += 1


            bf.seek(seek_pos)
            v = int(m.group(3), 16)
            bf.write(bytes([v]))
            count += 1

        ok, msg = True, (f"Applied {count} patche(s), with {nwarning} warning(s).")

    except Exception as e:
        ok, msg = False, f"At line {line_no}, seek {seek_pos:08X}, exception occured during patching: {str(e)}"
        #code.interact(local=locals())

    bf.close()
    df.close()

    return (ok, msg)

# --------------------------------------------------------------------------------------------
def show_help(err_msg = None):
    if err_msg is not None:
        print(f"Error parsing arguments: {err_msg}")

    print(f'{os.path.basename(sys.argv[0])} -i <diff inputfile> -o <bin outputfile> [-f (force)]')


# --------------------------------------------------------------------------------------------
def main(argv):
    verify = True
    bin_file = diff_file = None

    try:
        opts, args = getopt.getopt(argv, "fi:o:",["ifile=","ofile="])
    except getopt.GetoptError as e:
        show_help(str(e))
        return

    for opt, arg in opts:
        if opt == '-f':
            verify = False
        elif opt in ("-i", "--ifile"):
            diff_file = arg
        elif opt in ("-o", "--ofile"):
            bin_file = arg

    if bin_file is None or diff_file is None:
        show_help()
        return

    ok, msg = apply_diff(diff_file, bin_file, verify)
    if not ok:
        print(f"Error: {msg}")
    else:
        print(msg)

if __name__ == "__main__":
   main(sys.argv[1:])

