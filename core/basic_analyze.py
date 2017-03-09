#!/usr/bin/env python
# -*- coding:utf-8 -*-
# Malcode Analysis System
# version = 0.1
# author = felicitychou

import binascii
import hashlib
import os
import subprocess
import time

import magic
import pefile
import peutils
import ssdeep

from elftools.elf.elffile import ELFFile
from elftools.elf.descriptions import (
    describe_ei_class, describe_ei_data, describe_ei_version,
    describe_ei_osabi, describe_e_type, describe_e_machine,
    describe_e_version_numeric, describe_p_type, describe_p_flags,
    describe_sh_type, describe_sh_flags,
    describe_symbol_type, describe_symbol_bind, describe_symbol_visibility,
    describe_symbol_shndx, describe_reloc_type, describe_dyn_tag,
    describe_ver_flags, describe_note)

from conf import basic_conf




# filename filetype filesize md5 sha1
class BasicAnalyzer(object):

    def __init__(self,filepath,logger):

        self.filepath = filepath
        self.logger = logger
        self.run()

    def run(self):
        '''
        return {filename,filetype,filesize(Byte)}
        '''
        try:
            self.filename = os.path.basename(self.filepath)
            self.filetype = magic.from_file(self.filepath)
            self.filesize = int(os.path.getsize(self.filepath))
            self.hash = {"md5":self.hash_file('md5'),
                        "sha256":self.hash_file('sha256'),
                        "crc32":self.get_crc32(),
                        "ssdeep":self.get_ssdeep()}
            # get strings
            self.get_strings()
            self.strings = {"ascii":self.ascii_strings,"unicode":self.unicode_strings}

            # get info (include packer info)
            if self.filetype.startswith('PE32'):
                self.get_pe_info()
            elif self.filetype.startswith('ELF'):
                self.get_elf_info()

        except Exception as e:
            self.logger.exception('%s: %s' % (Exception, e))
            raise e

    # get packer info:
    def get_packer_info_pe(self,pe):
        # PE (PEid)
        # pe = pefile.PE(self.filepath)
        signatures = peutils.SignatureDatabase(basic_conf["PEidSign_path"])
        # matches is list()
        matches = signatures.match_all(pe, ep_only = True)
        self.packer = str(matches)

    def get_packer_info_elf(self):
        # ELF (UPX)
        cmd = [basic_conf["UPX_path"],"-q", "-t",self.filepath]
        output = subprocess.check_output(cmd)
        if -1!=output.find("[OK]"):
            self.packer = "upx"
        else:
            self.packer = None


    # get pe info
    def get_pe_info(self):

        # https://github.com/erocarrera/pefile/blob/wiki/UsageExamples.md#introduction
        # load pe
        pe = pefile.PE(self.filepath)
        self.get_packer_info_pe(pe = pe)
        #self.pe_info = pe.dump_info()

        self.pe_info = {}
        # Machine
        if hasattr(pe.FILE_HEADER,'Machine'):
            self.pe_info['Machine'] = hex(pe.FILE_HEADER.Machine)

        # TimeDateStamp
        if hasattr(pe.FILE_HEADER,'TimeDateStamp'):
            self.pe_info['TimeDataStamp'] = time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(pe.FILE_HEADER.TimeDateStamp))

        # AddressOfEntryPoint
        if hasattr(pe.OPTIONAL_HEADER,'AddressOfEntryPoint'):
            self.pe_info['AddressOfEntryPoint'] = hex(pe.OPTIONAL_HEADER.AddressOfEntryPoint)
        
        # Iterating through the sections
        if hasattr(pe,'sections'):
            self.pe_info['sections'] = [(section.Name, hex(section.VirtualAddress),hex(section.Misc_VirtualSize), hex(section.PointerToRawData), hex(section.SizeOfRawData)) for section in pe.sections]
        
        # Listing the imported symbols
        if hasattr(pe,'DIRECTORY_ENTRY_IMPORT'):
            import_info = {}
            for entry in pe.DIRECTORY_ENTRY_IMPORT:
                import_info[entry.dll] = [(hex(imp.address), imp.name) for imp in entry.imports]
        self.pe_info['DIRECTORY_ENTRY_IMPORT'] = import_info
        
        # Listing the exported symbols
        if hasattr(pe,'DIRECTORY_ENTRY_EXPORT'):
            self.pe_info['DIRECTORY_ENTRY_EXPORT']  = [(hex(pe.OPTIONAL_HEADER.ImageBase + exp.address), exp.name, exp.ordinal) for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols]


    # get elf info ？？？
    def get_elf_info(self):
        self.get_packer_info_elf()
        with open(self.filepath,'rb') as f:
            elffile = ELFFile(f)
            elffile.header
        self.elf_info['header'] = {'Magic':' '.join('%2.2x' % byte2int(b) for b in elffile.e_ident_raw),}


    def _parse_elf_info(self,elffile):

        header = {}
        e_ident = elffile.header['e_ident']
        header['Magic'] = ' '.join('%2.2x' % byte2int(b) for b in elffile.e_ident_raw)
        header['Class'] = '%s' % describe_ei_class(e_ident['e_ident']['EI_CLASS'])
        header['Data'] = '%s' % describe_ei_data(e_ident['e_ident']['EI_DATA'])        
        header['Version'] = '%s' % describe_ei_version(e_ident['EI_VERSION'])
        header['OS/ABI'] = '%s' %describe_ei_osabi(e_ident['EI_OSABI'])
        header['ABI Version'] = '%d' % e_ident['EI_ABIVERSION']
        header['Type'] = '%s' % describe_e_type(header['e_type'])
        header['Machine'] = '%s' % describe_e_machine(header['e_machine'])
        header['Version'] = '%s' % describe_e_version_numeric(header['e_version'])
        header['Entry point address'] = '%s' % self._format_hex(header['e_entry']))
        self._emit('  Start of program headers:          %s' %
                header['e_phoff'])
        self._emitline(' (bytes into file)')
        self._emit('  Start of section headers:          %s' %
                header['e_shoff'])
        self._emitline(' (bytes into file)')
        self._emitline('  Flags:                             %s%s' %
                (self._format_hex(header['e_flags']),
                self.decode_flags(header['e_flags'])))
        self._emitline('  Size of this header:               %s (bytes)' %
                header['e_ehsize'])
        self._emitline('  Size of program headers:           %s (bytes)' %
                header['e_phentsize'])
        self._emitline('  Number of program headers:         %s' %
                header['e_phnum'])
        self._emitline('  Size of section headers:           %s (bytes)' %
                header['e_shentsize'])
        self._emitline('  Number of section headers:         %s' %
                header['e_shnum'])
        self._emitline('  Section header string table index: %s' %
                header['e_shstrndx'])


    # get strings unicode and ascii 
    def get_strings(self):
        # windows
        # strings.exe https://technet.microsoft.com/en-us/sysinternals/bb897439.aspx

        # linux
        self.ascii_strings = subprocess.check_output(["strings", "-a", self.filepath])
        self.unicode_strings = subprocess.check_output(["strings", "-a", "-el", self.filepath])
        #return ascii_strings, unicode_strings

    # get hash ('md5', 'sha1', 'sha224', 'sha256', 'sha384', 'sha512')
    def hash_file(self, hash_type):
        try:
            hash_handle = getattr(hashlib, hash_type)()
            with open(self.filepath, 'rb') as file:
                hash_handle.update(file.read())
            return hash_handle.hexdigest()
        except Exception as e:
            raise e
        
    # get crc32
    def get_crc32(self):
        try:
            with open(self.filepath, 'rb') as file:
                return '%x' % (binascii.crc32(file.read()) & 0xffffffff)
        except Exception as e:
            raise e

    # get ssdeep
    def get_ssdeep(self):
        try:
            return ssdeep.hash_from_file(self.filepath)
        except Exception as e:
            raise e
        
    # output
    def output(self):
        try:
            result = {}
            for item in ('filename','filetype','filesize')
                result[item] = getattr(self,item)
            result.update(self.hash)
            return result
        except Exception as e:
            raise e


    # output json
