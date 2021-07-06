import os, sys, re, getopt
#import code
"""
Apply a DIFF file to a binary file.


A DIFF file can be generated from IDA Pro for example or the output of "FC.EXE /B file1.bin file2.bin
"""

# TODO:
# -- make as an IDA plugin
# -- add "Apply DIF" menu
# -- refactor
def apply_diff(diff_file, bin_file, verify):
    # Get the binary file size
    try:
        bin_size = os.path.getsize(bin_file)
    except:
        return (False, "Binary file '%s' not found!" % bin_file)

    # Open the binary file for updates
    try:
        bf = open(bin_file, 'r+b')
    except:
        return (False, "Binary file '%s' could not be open for updates" % bin_file)

    # Compile the regular expression
    diff_re = re.compile(r'^([0-9a-f]+): ([0-9a-f]{2}) ([0-9a-f]{2})$', re.IGNORECASE)

    # Open the diff file
    try:
        df = open(diff_file, 'r')
    except:
        bf.close()
        return (False, "Diff file '%s' could not be open for reading" % diff_file)

    # Read the diff file
    count = 0
    line_no = 0
    try:
        for line in df:
            line_no += 1
            m = diff_re.match(line.strip())
            if not m:
                continue

            seek_pos = int(m.group(1), 16)
            if seek_pos > bin_size:
                raise Exception("Seek position 0x%X in diff file is greater than the file size!" % (seek_pos))

            if verify:
                bf.seek(seek_pos)
                v = ord(bf.read(1))
                o = int(m.group(2), 16)

                if v != o:
                    print("WARNING: verification failed. Original byte %02X is expected, %02X found instead. Skipping." % (o, v))

            bf.seek(seek_pos)
            v = int(m.group(3), 16)
            bf.write(bytes([v]))
            count += 1

        ok, msg = True, ("Applied %d patche(s)" % count)

    except Exception as e:
        ok, msg = False, "At line %d, seek %08X, exception occured during patching: %s" % (line_no, seek_pos, str(e))
        #code.interact(local=locals())


    bf.close()
    df.close()

    return (ok, msg)


def show_help(err_msg = None):
    if err_msg is not None:
        print("Error parsing arguments: %s " % err_msg)

    print('%s -i <diff inputfile> -o <bin outputfile> [-f (force)]' % os.path.basename(sys.argv[0]))


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
        print("Error: %s" % msg)
    else:
        print(msg)

if __name__ == "__main__":
   main(sys.argv[1:])

