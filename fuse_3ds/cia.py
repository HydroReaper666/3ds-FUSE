import struct
from . import ticket
from . import tmd
import hashlib
import sys
from Crypto.Cipher import AES
def align(x,y):
    mask = ~(y-1)
    return (x+(y-1))&mask
class CIA:
    def __init__(self, f):
        self.f=f
        self.headerSize,self.type,self.version,self.cachainSize,self.tikSize,self.tmdSize,self.metaSize,self.contentSize=struct.unpack("<IHHIIIIQ",self.f.read(0x20))
        self.cachainOff=align(self.headerSize,64)
        self.tikOff=align(self.cachainOff+self.cachainSize,64)
        self.tmdOff=align(self.tikOff+self.tikSize,64)
        self.contentOff=align(self.tmdOff+self.tmdSize,64)
        self.metaOff=align(self.contentOff+self.contentSize,64)
        self.contentIndex=self.f.read(0x2000)
        for e,f,g in [("Header:",0,self.headerSize),("CA chain",self.cachainOff,self.cachainSize),("Ticket:",self.tikOff,self.tikSize),("TMD:",self.tmdOff,self.tmdSize),("Content:",self.contentOff,self.contentSize),("Metadata:",self.metaOff,self.metaSize)]:
            print(e,hex(f),hex(g))
        self.f.seek(self.cachainOff)
        self.cachain=self.f.read(self.cachainSize)
        self.f.seek(self.tikOff)
        self.ticket=ticket.Ticket(self.f)
        self.f.seek(self.tmdOff)
        self.tmd=tmd.TMD(self.f)
        self.ticket.decryptTitleKey(self.tmd.tid)
        self.f.seek(self.contentOff)
        self.size=self.metaOff+self.metaSize
        off=0
    def hashCheck(self):
        print("Doing hash checks. This may take a while")
        self.f.seek(self.contentOff)
        secno=0
        for no,content in enumerate(self.tmd.contents):
            sha=hashlib.sha256()
            for cno in range(content["size"]//512):
                sha.update(self.read(secno))
                if not cno % 2048:
                    print(".",end="")
                    sys.stdout.flush()
                secno+=1
            print()
            sha=sha.digest()
            if sha != self.tmd.contentHashes[no]:
                print("WARNING: Section",no,"hash mismatch!")
    def startSec(self,cid):
        byte=0
        for f in self.tmd.contents:
            if cid==f["index"]:
                return byte//512
            byte+=f["size"]
    def getContentNo(self,sector):
        byte=sector*512
        for f in self.tmd.contents:
            if byte < f["size"]:
                return f["index"]
            byte-=f["size"]
    def contentSector(self,sector):
        byte=sector*512
        for f in self.tmd.contents:
            if byte < f["size"]:
                return byte//512
            byte-=f["size"]
    def getDecHeader(self):
        header=struct.pack("<IHHIIIIQ",self.headerSize,self.type,self.version,self.cachainSize,self.tikSize,self.tmdSize,self.metaSize,self.contentSize)
        header+=self.contentIndex
        #Decrypting ticket and tmd
        header+=bytes(self.cachainOff-len(header))
        header+=self.cachain
        header+=bytes(self.tikOff-len(header))
        header+=self.ticket.decrypt()
        header+=bytes(self.tmdOff-len(header))
        header+=self.tmd.decrypt()
        header+=bytes(self.contentOff-len(header))
        return header
    def read(self,sectorno,sectors=1):
        """
        NOTE: Only reads whole sectors!
        """
        self.f.seek(self.contentOff+sectorno*512)
        if not self.tmd.contents[self.getContentNo(sectorno)]["type"]&1:
            #Just read the unencrypted data
            return self.f.read(sectors*512)
        iv=b''
        if not self.contentSector(sectorno):
            iv=self.tmd.contents[self.getContentNo(sectorno)]["index"].to_bytes(2,byteorder="big")+b'\x00'*14
        else:
            self.f.seek((self.contentOff+sectorno*512)-16)
            iv=self.f.read(16)
        cipher=AES.new(self.ticket.titlekey, AES.MODE_CBC, iv)
        return cipher.decrypt(self.f.read(sectors*512))
