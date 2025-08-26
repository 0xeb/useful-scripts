import re, copy, sys

# Preprocess return
PP_SKIP = 0
"""Skip this block. Usually used with the IFDEF blocks"""
PP_OK = 1
"""Accept the current block"""
PP_REPEAT = 2
"""Repeat this block"""
PP_ABORT = 3
"""Abort the preprocessing"""

# Element kinds
EL_BLOCK = 0
"""A block with start/end"""
EL_IFDEF_BLOCK = 1
"""IfDef block"""
EL_EXEC        = 2
"""Exec line"""
EL_LINE        = 3
"""Regular line"""

CONTAINER_ELEMENTS = (EL_BLOCK, EL_IFDEF_BLOCK)
"""Elements that contain sub-elements"""

# ------------------------------------------------------------
class element_t(object):
    """Base element"""
    IDS = 0
    def __init__(self, line_no = 0):
        self.IDS += 1
        self.__id = self.IDS

        self.line_no = line_no
        """Element line number / location"""
        self.kind = None
        """Element kind"""

    id = property(lambda self: self.__id)
    """Unique item ID"""

    def is_container(self):
        return self.kind in CONTAINER_ELEMENTS


# ------------------------------------------------------------
class line_t(element_t):
    """Regular line"""
    def __init__(self, line_no, line):
        super(line_t, self).__init__(line_no = line_no)
        self.line = line
        self.kind = EL_LINE

    def __str__(self):
        return self.line

    def __repr__(self):
        return "line(%d, '%s')" % (self.line_no, self.line)


# ------------------------------------------------------------
class block_t(element_t):
    def __init__(self, line_no, tag, indent=0):
        super(block_t, self).__init__(line_no = line_no)
        self.tag  = tag
        self.kind = EL_BLOCK
        self.indent = indent
        self.elements = []
        """Array of elements"""

    def add_element(self, element):
        """Adds an element and returns it back"""
        self.elements.append(element)
        return element

    def __str__(self):
        return ""

    def __repr__(self, line_no, tag):
        return "block(%d, %s)" % (self.lino_no, self.tag)


# ------------------------------------------------------------
class ifdef_block_t(block_t):
    def __init__(self, line_no, condition):
        super(ifdef_block_t, self).__init__(line_no = line_no, tag=condition)
        self.kind = EL_IFDEF_BLOCK

    condition = property(fget=lambda self: self.tag)

    def __str__(self):
        return "#ifdef %s" % self.tag

    def __repr__(self, line_no, tag):
        return "ifdef(%d, %s)" % (self.lino_no, self.tag)


# ------------------------------------------------------------
class exec_t(element_t):
    def __init__(self, line_no, stmt, indent):
        super(exec_t, self).__init__(line_no = line_no)
        self.stmt = stmt
        self.indent = indent
        self.kind = EL_EXEC
        """Array of elements"""

    def get_indent_string(self):
        return ' ' * self.indent

    def __str__(self):
        return "<exec(%s)>" % self.stmt

    def __repr__(self, line_no, tag):
        return "<exec(%d, %s)>" % (self.lino_no, self.stmt)


# ------------------------------------------------------------
class preprocess_t(object):
    RE_BLOCK_BEGIN = re.compile(r'^.*!BLOCK_BEGIN ([^\s]+).*', re.I)
    RE_BLOCK_END   = re.compile(r'^.*!BLOCK_END ([^\s]+).*', re.I)
    RE_IFDEF       = re.compile(r'^.*!IFDEF (.*)', re.I)
    RE_ENDIF       = re.compile(r'^.*!ENDIF (.*)', re.I)
    RE_EXEC        = re.compile(r'^(.*)!EXEC (.*)', re.I)
    RE_VAR_WRAP    = re.compile(r'\$(\w+)\$', re.I)

    def __init__(self):
        self.reset()

    def _re_expand(self, match):
        var_name = match.group(1)
        return self.get_var(var_name, '')

    def reset(self):
        self.environments = []
        """The environment variables within an active block"""
        self.active_environment = {'self': self}
        """Variables for the current environment"""
        self.elements = []
        """Top level elements"""
        self.active_block = None
        """Current block or None"""
        self.blocks = []
        """Blocks stack used by the parser"""
        self.defines = {}
        """Preprocessor defines"""
        self.output = []
        """The emitted output from the preprocessor and its handlers"""


    def set_var(self, name, value):
        if name == 'self':
            raise Exception("Cannot change reserved value!")

        self.active_environment[name] = str(value)

    def get_var(self, name, defval=None):
        return self.active_environment.get(name, defval)

    def define(self, var, value=None):
        self.defines[var] = value

    def is_defined(self, var):
        return var in self.defines

    def get_definition(self, var, defval=None):
        return self.defines.get(var, defval)

    def on_block_enter(self, block):
        """Called when a block is entered
        Return:
            PP_SKIP    : to skip this block and its subblocks
            PP_OK      : to process this block
            PP_ABORT   : to abort the preprocessor
        """
        return PP_OK

    def on_block_exit(self, block):
        """Called when a block is left
        Return:
            PP_REPEAT  : to repeat this block and its subblocks
            PP_OK      : to moveon to next blocks
            PP_ABORT   : to abort the preprocessor
        """
        return PP_OK

    def on_preexec(self, exec_directive, stmt):
        """Called when an execute directive is found and before it gets executed
        Return:
            PP_OK      : to accept this block and execute it
            PP_SKIP    : to skip execution of this block
            PP_ABORT   : to abort the preprocessor
        """
        return PP_OK

    def on_postexec(self, exec_directive, stmt):
        """Called when an execute directive is found and was executed
        Return:
            PP_OK      : to moveon
            PP_ABORT   : to abort the preprocessor
        """
        return PP_OK

    def pre_exec_indent(self, exec_directive):
        self.emit(exec_directive.get_indent_string())

    def emit(self, s):
        s = self.expand(s)
        self.output.append(s)

    def emit_line(self, line):
        if line[-1] == "\n":
            self.emit(line)
        else:
            self.emit(line + "\n")


    def expand(self, s):
        """Expand a string using the active environment"""
        return self.RE_VAR_WRAP.sub(self._re_expand, s)


    def eval_ifdef(self, condition):
        try:
            # Evaluate the condition
            result = bool(eval(condition, globals=globals(), locals=self.defines))
            return PP_OK if result else PP_SKIP
        except:
            return PP_SKIP


    def exec_stmt(self, stmt):
        try:
            # Evaluate the condition
            exec(stmt, globals(), self.active_environment)
            return PP_OK
        except Exception as e:
            print("Exception: %s" % e)
            return PP_ABORT


    def push_environment(self):
        # Push current environment
        self.environments.append(self.environment)
        # Take a copy of the current environment
        self.active_environment = copy.deepcopy(self.active_environment)


    def pop_environment(self):
        if len(self.environments):
            self.environment = self.environments.pop()


    def push_block(self, switch=None):
        self.blocks.append(self.active_block)
        if switch is not None:
            self.switch_block(switch)

    def switch_block(self, new_block):
        self.active_block = new_block

    def pop_block(self, tag):
        if not len(self.blocks):
            raise Exception("Unbalanced nesting")

        if self.active_block.tag != tag:
            raise Exception("Unexpected tag value")
        self.switch_block(self.blocks.pop())


    def block_begin(self, line_no, m):
        self.push_environment()


    def add_element(self, element):
        """Adds an element and returns it back"""
        if self.active_block is None:
            self.elements.append(element)
        else:
            self.active_block.add_element(element)
        return element


    def is_block_begin(self, line):
        m = self.RE_BLOCK_BEGIN.search(line)
        if m:
            return (m, block_t)
        m = self.RE_IFDEF.search(line)
        if m:
            return (m, ifdef_block_t)

        return (None, None)


    def is_block_end(self, line):
        m = self.RE_BLOCK_END.search(line)
        if m:
            return m
        return self.RE_ENDIF.search(line)


    def parse(self, lines):
        """Parse a set of lines. Do this once. Afterwards, you can call Eval() as many times as you want"""
        self.reset()
        if type(lines) is str:
            lines = lines.split("\n")

        line_no = 0
        for line in lines:
            line_no += 1

            # Block begin?
            m, block_class = self.is_block_begin(line)
            if block_class:
                new_block = block_class(line_no, m.group(1))
                self.push_block(switch=self.add_element(new_block))
                continue
            # Block end?
            m = self.is_block_end(line)
            if m:
                self.pop_block(m.group(1))
                continue

            m = self.RE_EXEC.search(line)
            if m:
                element = exec_t(line_no, stmt=m.group(2), indent=m.end(1))
            else:
                element = line_t(line_no, line)

            # Regular line
            self.add_element(element)


    def visit(self, callback, elements=None):
        if elements is None:
            elements = self.elements

        for element in elements:
            if element.is_container():
                ok = self.visit(callback=callback, elements=element.elements)
            else:
                ok = callback(element)
            if not ok:
                return False

        return True


    def dump(self, elements=None, indent=''):
        if elements is None:
            footer = True
            elements = self.elements
        else:
            footer = False

        for i, element in enumerate(elements):
            sys.stdout.write("%03d%s>" % (element.line_no, indent))
            if element.is_container():
                print("<container %s>" % element.tag)
                self.dump(element.elements, indent=indent + '  ')
                sys.stdout.write("%03d%s></container %s>\n" % (element.line_no, indent, element.tag))
            else:
                print("%s" % element)


        if footer:
            print("----------------")


    def pprint(self, elements=None):
        def callback(element):
            if element.kind == EL_LINE:
                print(str(element))
            return True

        self.visit(callback=callback)


    def eval(self, elements=None):
        """Evaluates a previously parsed template"""
        if elements is None:
            elements = self.elements

        for element in elements:
            if element.kind == EL_IFDEF_BLOCK:
                # Evaluate and see if we need to skip this block
                if self.eval_ifdef(element.condition) == PP_SKIP:
                    continue
                # Walk the elements in this protected block
                if self.eval(element.elements) == PP_ABORT:
                    return PP_ABORT
                else:
                    continue
            elif element.kind == EL_BLOCK:
                # Potentially, this block might be repeated
                while True:
                    # Before recursing into block elements
                    ret = self.on_block_enter(element)
                    if ret == PP_ABORT:
                        return ret
                    # Block should be fully explored?
                    elif ret == PP_SKIP:
                        break
                    # Explore the block
                    ret = self.eval(element.elements)
                    if ret == PP_ABORT:
                        return ret
                    # Notify about the block end
                    ret = self.on_block_exit(element)
                    if ret == PP_ABORT:
                        return ret
                    # Don't repeat the block unless required
                    elif ret == PP_REPEAT:
                        continue
                    # Don't repeat this block
                    break
                continue
            elif element.kind == EL_LINE:
                self.emit_line(element.line)
            elif element.kind == EL_EXEC:
                stmt = self.expand(element.stmt)
                ret = self.on_preexec(element, stmt)
                if ret == PP_ABORT:
                    return ret
                elif ret == PP_SKIP:
                    break
                # Execute the statement
                if self.exec_stmt(stmt) == PP_ABORT:
                    return PP_ABORT
                if self.on_postexec(element, stmt) == PP_ABORT:
                    return PP_ABORT
                continue


        return "".join(self.output)


def main():
    """Main function for command-line usage."""
    import argparse
    parser = argparse.ArgumentParser(description='Text preprocessor with conditional blocks and variable expansion')
    parser.add_argument('input_file', help='Input file to preprocess')
    parser.add_argument('-o', '--output', help='Output file (default: stdout)')
    parser.add_argument('-D', '--define', action='append', default=[], 
                        help='Define a variable (format: VAR=VALUE or VAR)')
    
    args = parser.parse_args()
    
    # Read input file
    with open(args.input_file, 'r') as f:
        text = f.read()
    
    # Create preprocessor instance
    pp = preproc_t()
    
    # Set up defined variables
    for define in args.define:
        if '=' in define:
            var, val = define.split('=', 1)
            pp.set_var(var, val)
        else:
            pp.set_var(define, '1')
    
    # Process the text
    result = pp.process(text)
    
    # Output result
    if args.output:
        with open(args.output, 'w') as f:
            f.write(result)
    else:
        print(result, end='')


if __name__ == '__main__':
    main()
