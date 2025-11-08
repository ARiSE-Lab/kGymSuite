import asyncio.subprocess as asp
import re

async def count_instructions(binary_file, source_file):
    proc = await asp.create_subprocess_exec(
        'objdump', '-d', '-l', binary_file,
        stdin=asp.DEVNULL, stdout=asp.PIPE, stderr=asp.PIPE
    )

    stdout, _ = await proc.communicate()
    stdout = stdout.decode()

    code = await proc.wait()

    d = {}
    symb = set()
    function_pattern = r"^[0-9a-f]+ <([a-zA-Z0-9_\.]+)>:$"
    file_specifier_pattern = r"(.+):\d+$"

    in_function = False
    correct_file = False
    function_name = ''
    instructions_count = 0
    for line in stdout.splitlines():
        if not in_function:
            match = re.search(function_pattern, line)
            if match:
                function_name = match.group(1)
                in_function = True
                instructions_count = 0
        else:
            if line.strip() == '':  
                in_function = False
                if correct_file:
                    correct_file = False
                    d[function_name] = instructions_count
                    symb.add(function_name)
                continue
            if not correct_file:
                file_match = re.search(file_specifier_pattern, line)            
                if file_match:
                    file_path = file_match.group(1)
                    if source_file in file_path:
                        correct_file = True
                    continue
            elif line[-3:] != '():':
                instructions_count += 1
    return d, len(symb), symb

async def compare_binaries_subutil(file1, file2, source_file):
    dict1, _, symb1 = await count_instructions(file1, source_file)
    dict2, _, symb2 = await count_instructions(file2, source_file)

    modified_functions = []
    for symb in symb1:
        if symb in symb2:
            diff = abs(dict1[symb] - dict2[symb])
            if diff > 0:
                modified_functions.append({
                    'function-name': symb,
                    'instruction-count-before': dict1[symb],
                    'instruction-count-after': dict2[symb]
                })

    for symb in symb1 - symb2:
        modified_functions.append({
            'function-name': symb,
            'instruction-count-before': dict1[symb],
            'instruction-count-after': 0
        })
    for symb in symb2 - symb1:
        modified_functions.append({
            'function-name': symb,
            'instruction-count-before': 0,
            'instruction-count-after': dict2[symb]
        })

    return modified_functions