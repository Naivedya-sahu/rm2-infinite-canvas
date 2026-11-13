"""Read ARM32 xochitl Qt resources offline. Never executes tablet code.

Dependencies: pyelftools, capstone, PySide6-Essentials.
Recognizes straight-line ARM resource registration sequences, fails on missing resources.
"""
from collections import deque
from pathlib import Path
import io
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from elftools.elf.elffile import ELFFile
from PySide6.QtCore import QDir, QDirIterator, QFile, QIODevice, QResource


def extract(binary):
    blob = Path(binary).read_bytes()
    elf = ELFFile(io.BytesIO(blob))
    if elf['e_machine'] != 'EM_ARM' or elf.elfclass != 32 or not elf.little_endian:
        raise ValueError('Only little-endian ARM32 ELF is supported')
    symbols = elf.get_section_by_name('.dynsym')
    relocations = elf.get_section_by_name('.rel.plt')
    registrations = [i for i, r in enumerate(relocations.iter_relocations())
                     if symbols.get_symbol(r['r_info_sym']).name == '_Z21qRegisterResourceDataiPKhS0_S0_']
    if len(registrations) != 1:
        raise ValueError('Ambiguous Qt registration import')
    # GNU ARM PLT: 20-byte resolver, 12-byte import stubs.
    target = elf.get_section_by_name('.plt')['sh_addr'] + 20 + 12 * registrations[0]
    text = elf.get_section_by_name('.text')
    disassembler = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    disassembler.skipdata = True
    history = deque(maxlen=18)
    tables = set()
    for address, size, mnemonic, operands in disassembler.disasm_lite(text.data(), text['sh_addr']):
        if mnemonic == 'bl' and operands == f'#{target:#x}':
            registers = {}
            for m, o in history:
                args = o.split(', ')
                if m in ('mov', 'movw', 'movt') and len(args) == 2:
                    dst, value = args
                    if value.startswith('#'):
                        value = int(value[1:], 0)
                        registers[dst] = ((registers.get(dst, 0) & 65535) | value << 16) if m == 'movt' else value
                    elif value in registers:
                        registers[dst] = registers[value]
                    else:
                        registers.pop(dst, None)
                elif m == 'add' and len(args) == 3:
                    dst, src, value = args
                    if src in registers and value.startswith('#'):
                        registers[dst] = registers[src] + int(value[1:], 0)
                    else:
                        registers.pop(dst, None)
                elif m in ('bl', 'b', 'bx'):
                    registers.clear()
            if all(k in registers for k in ('r0', 'r1', 'r2', 'r3')) and registers['r0'] == 3:
                tables.add(tuple(registers[k] for k in ('r1', 'r2', 'r3')))
        history.append((mnemonic, operands))
    if not tables:
        raise ValueError('No Qt resource tables recognized')

    def offset(address):
        for segment in elf.iter_segments():
            start = segment['p_vaddr']
            if start <= address < start + segment['p_filesz']:
                return segment['p_offset'] + address - start
        raise ValueError('Resource pointer outside file')

    result = {}
    for tree, names, data in sorted(tables):
        payload = struct.pack('>4sIIIII', b'qres', 3, offset(tree) + 24,
                              offset(data) + 24, offset(names) + 24, 0) + blob
        if not QResource.registerResourceData(payload):
            raise ValueError('Qt rejected extracted resource table')
        try:
            iterator = QDirIterator(':/', ['*.qml', '*.js'], QDir.Filter.Files,
                                    QDirIterator.IteratorFlag.Subdirectories)
            while iterator.hasNext():
                name = iterator.next()
                resource = QResource(name)
                packed = bytes(resource.data())
                if resource.compressionAlgorithm() == QResource.Compression.ZstdCompression:
                    import zstandard
                    contents = zstandard.ZstdDecompressor().decompress(packed)
                elif resource.compressionAlgorithm() == QResource.Compression.ZlibCompression:
                    import zlib
                    contents = zlib.decompress(packed[4:])
                else:
                    contents = packed
                result[name[1:]] = contents
        finally:
            QResource.unregisterResourceData(payload)
    return result


if __name__ == '__main__':
    import argparse
    import hashlib
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    resources = extract(args.binary)
    args.output.mkdir(parents=True, exist_ok=False)
    for name, contents in resources.items():
        dest = args.output / name.lstrip('/')
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(contents)
    (args.output / 'index.json').write_text(json.dumps({name: hashlib.sha256(data).hexdigest()
        for name, data in resources.items()}, indent=2), encoding='utf-8')
    print(f'Extracted {len(resources)} QML/JS resources offline')
