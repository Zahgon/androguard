# This file is part of Androguard.
#
# Copyright (C) 2012, Geoffroy Gueguen <geoffroy.gueguen@gmail.com>
# All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from struct import pack, unpack

from loguru import logger

import androguard.decompiler.util as util
from androguard.decompiler.instruction import (
    ArrayLengthExpression,
    ArrayLoadExpression,
    ArrayStoreInstruction,
    AssignExpression,
    BaseClass,
    BinaryCompExpression,
    BinaryExpression,
    BinaryExpression2Addr,
    BinaryExpressionLit,
    CastExpression,
    CheckCastExpression,
    ConditionalExpression,
    ConditionalZExpression,
    Constant,
    FillArrayExpression,
    FilledArrayExpression,
    InstanceExpression,
    InstanceInstruction,
    InvokeDirectInstruction,
    InvokeInstruction,
    InvokeRangeInstruction,
    InvokeStaticInstruction,
    MonitorEnterExpression,
    MonitorExitExpression,
    MoveExceptionExpression,
    MoveExpression,
    MoveResultExpression,
    NewArrayExpression,
    NewInstance,
    NopExpression,
    ReturnInstruction,
    StaticExpression,
    StaticInstruction,
    SwitchExpression,
    ThisParam,
    ThrowExpression,
    UnaryExpression,
    Variable,
)


class Op:
    CMP = 'cmp'
    ADD = '+'
    SUB = '-'
    MUL = '*'
    DIV = '/'
    MOD = '%'
    AND = '&'
    OR = '|'
    XOR = '^'
    EQUAL = '=='
    NEQUAL = '!='
    GREATER = '>'
    LOWER = '<'
    GEQUAL = '>='
    LEQUAL = '<='
    NEG = '-'
    NOT = '~'
    INTSHL = '<<'  # '(%s << ( %s & 0x1f ))'
    INTSHR = '>>'  # '(%s >> ( %s & 0x1f ))'
    LONGSHL = '<<'  # '(%s << ( %s & 0x3f ))'
    LONGSHR = '>>'  # '(%s >> ( %s & 0x3f ))'


def get_variables(vmap, *variables):
    res = []
    for variable in variables:
        res.append(vmap.setdefault(variable, Variable(variable)))
    if len(res) == 1:
        return res[0]
    return res


















## From here on, there are all defined instructions


# nop


# move vA, vB ( 4b, 4b )
def move(ins, vmap):
    logger.debug('Move %s', ins.get_output())
    reg_a, reg_b = get_variables(vmap, ins.A, ins.B)
    return MoveExpression(reg_a, reg_b)


# move/from16 vAA, vBBBB ( 8b, 16b )


# move/16 vAAAA, vBBBB ( 16b, 16b )


# move-wide vA, vB ( 4b, 4b )


# move-wide/from16 vAA, vBBBB ( 8b, 16b )


# move-wide/16 vAAAA, vBBBB ( 16b, 16b )


# move-object vA, vB ( 4b, 4b )


# move-object/from16 vAA, vBBBB ( 8b, 16b )


# move-object/16 vAAAA, vBBBB ( 16b, 16b )


# move-result vAA ( 8b )


# move-result-wide vAA ( 8b )


# move-result-object vAA ( 8b )


# move-exception vAA ( 8b )


# return-void


# return vAA ( 8b )


# return-wide vAA ( 8b )


# return-object vAA ( 8b )


# const/4 vA, #+B ( 4b, 4b )


# const/16 vAA, #+BBBB ( 8b, 16b )


# const vAA, #+BBBBBBBB ( 8b, 32b )


# const/high16 vAA, #+BBBB0000 ( 8b, 16b )


# const-wide/16 vAA, #+BBBB ( 8b, 16b )


# const-wide/32 vAA, #+BBBBBBBB ( 8b, 32b )


# const-wide vAA, #+BBBBBBBBBBBBBBBB ( 8b, 64b )


# const-wide/high16 vAA, #+BBBB000000000000 ( 8b, 16b )


# const-string vAA ( 8b )


# const-string/jumbo vAA ( 8b )


# const-class vAA, type@BBBB ( 8b )


# monitor-enter vAA ( 8b )


# monitor-exit vAA ( 8b )


# check-cast vAA ( 8b )


# instance-of vA, vB ( 4b, 4b )


# array-length vA, vB ( 4b, 4b )


# new-instance vAA ( 8b )


# new-array vA, vB ( 8b, size )


# filled-new-array {vD, vE, vF, vG, vA} ( 4b each )


# filled-new-array/range {vCCCC..vNNNN} ( 16b )


# fill-array-data vAA, +BBBBBBBB ( 8b, 32b )


# fill-array-data-payload vAA, +BBBBBBBB ( 8b, 32b )


# throw vAA ( 8b )


# goto +AA ( 8b )


# goto/16 +AAAA ( 16b )


# goto/32 +AAAAAAAA ( 32b )


# packed-switch vAA, +BBBBBBBB ( reg to test, 32b )


# sparse-switch vAA, +BBBBBBBB ( reg to test, 32b )


# cmpl-float vAA, vBB, vCC ( 8b, 8b, 8b )


# cmpg-float vAA, vBB, vCC ( 8b, 8b, 8b )


# cmpl-double vAA, vBB, vCC ( 8b, 8b, 8b )


# cmpg-double vAA, vBB, vCC ( 8b, 8b, 8b )


# cmp-long vAA, vBB, vCC ( 8b, 8b, 8b )


# if-eq vA, vB, +CCCC ( 4b, 4b, 16b )


# if-ne vA, vB, +CCCC ( 4b, 4b, 16b )


# if-lt vA, vB, +CCCC ( 4b, 4b, 16b )


# if-ge vA, vB, +CCCC ( 4b, 4b, 16b )


# if-gt vA, vB, +CCCC ( 4b, 4b, 16b )


# if-le vA, vB, +CCCC ( 4b, 4b, 16b )


# if-eqz vAA, +BBBB ( 8b, 16b )


# if-nez vAA, +BBBB ( 8b, 16b )


# if-ltz vAA, +BBBB ( 8b, 16b )


# if-gez vAA, +BBBB ( 8b, 16b )


# if-gtz vAA, +BBBB ( 8b, 16b )


# if-lez vAA, +BBBB (8b, 16b )


# TODO: check type for all aget
# aget vAA, vBB, vCC ( 8b, 8b, 8b )


# aget-wide vAA, vBB, vCC ( 8b, 8b, 8b )


# aget-object vAA, vBB, vCC ( 8b, 8b, 8b )


# aget-boolean vAA, vBB, vCC ( 8b, 8b, 8b )


# aget-byte vAA, vBB, vCC ( 8b, 8b, 8b )


# aget-char vAA, vBB, vCC ( 8b, 8b, 8b )


# aget-short vAA, vBB, vCC ( 8b, 8b, 8b )


# aput vAA, vBB, vCC


# aput-wide vAA, vBB, vCC ( 8b, 8b, 8b )


# aput-object vAA, vBB, vCC ( 8b, 8b, 8b )


# aput-boolean vAA, vBB, vCC ( 8b, 8b, 8b )


# aput-byte vAA, vBB, vCC ( 8b, 8b, 8b )


# aput-char vAA, vBB, vCC ( 8b, 8b, 8b )


# aput-short vAA, vBB, vCC ( 8b, 8b, 8b )


# iget vA, vB ( 4b, 4b )


# iget-wide vA, vB ( 4b, 4b )


# iget-object vA, vB ( 4b, 4b )


# iget-boolean vA, vB ( 4b, 4b )


# iget-byte vA, vB ( 4b, 4b )


# iget-char vA, vB ( 4b, 4b )


# iget-short vA, vB ( 4b, 4b )


# iput vA, vB ( 4b, 4b )


# iput-wide vA, vB ( 4b, 4b )


# iput-object vA, vB ( 4b, 4b )


# iput-boolean vA, vB ( 4b, 4b )


# iput-byte vA, vB ( 4b, 4b )


# iput-char vA, vB ( 4b, 4b )


# iput-short vA, vB ( 4b, 4b )


# sget vAA ( 8b )


# sget-wide vAA ( 8b )


# sget-object vAA ( 8b )


# sget-boolean vAA ( 8b )


# sget-byte vAA ( 8b )


# sget-char vAA ( 8b )


# sget-short vAA ( 8b )


# sput vAA ( 8b )


# sput-wide vAA ( 8b )


# sput-object vAA ( 8b )


# sput-boolean vAA ( 8b )


# sput-wide vAA ( 8b )


# sput-char vAA ( 8b )


# sput-short vAA ( 8b )




# invoke-virtual {vD, vE, vF, vG, vA} ( 4b each )


# invoke-super {vD, vE, vF, vG, vA} ( 4b each )


# invoke-direct {vD, vE, vF, vG, vA} ( 4b each )


# invoke-static {vD, vE, vF, vG, vA} ( 4b each )


# invoke-interface {vD, vE, vF, vG, vA} ( 4b each )


# invoke-virtual/range {vCCCC..vNNNN} ( 16b each )


# invoke-super/range {vCCCC..vNNNN} ( 16b each )


# invoke-direct/range {vCCCC..vNNNN} ( 16b each )


# invoke-static/range {vCCCC..vNNNN} ( 16b each )


# invoke-interface/range {vCCCC..vNNNN} ( 16b each )


# neg-int vA, vB ( 4b, 4b )


# not-int vA, vB ( 4b, 4b )


# neg-long vA, vB ( 4b, 4b )


# not-long vA, vB ( 4b, 4b )


# neg-float vA, vB ( 4b, 4b )


# neg-double vA, vB ( 4b, 4b )


# int-to-long vA, vB ( 4b, 4b )


# int-to-float vA, vB ( 4b, 4b )


# int-to-double vA, vB ( 4b, 4b )


# long-to-int vA, vB ( 4b, 4b )


# long-to-float vA, vB ( 4b, 4b )


# long-to-double vA, vB ( 4b, 4b )


# float-to-int vA, vB ( 4b, 4b )


# float-to-long vA, vB ( 4b, 4b )


# float-to-double vA, vB ( 4b, 4b )


# double-to-int vA, vB ( 4b, 4b )


# double-to-long vA, vB ( 4b, 4b )


# double-to-float vA, vB ( 4b, 4b )


# int-to-byte vA, vB ( 4b, 4b )


# int-to-char vA, vB ( 4b, 4b )


# int-to-short vA, vB ( 4b, 4b )


# add-int vAA, vBB, vCC ( 8b, 8b, 8b )


# sub-int vAA, vBB, vCC ( 8b, 8b, 8b )


# mul-int vAA, vBB, vCC ( 8b, 8b, 8b )


# div-int vAA, vBB, vCC ( 8b, 8b, 8b )


# rem-int vAA, vBB, vCC ( 8b, 8b, 8b )


# and-int vAA, vBB, vCC ( 8b, 8b, 8b )


# or-int vAA, vBB, vCC ( 8b, 8b, 8b )


# xor-int vAA, vBB, vCC ( 8b, 8b, 8b )


# shl-int vAA, vBB, vCC ( 8b, 8b, 8b )


# shr-int vAA, vBB, vCC ( 8b, 8b, 8b )


# ushr-int vAA, vBB, vCC ( 8b, 8b, 8b )


# add-long vAA, vBB, vCC ( 8b, 8b, 8b )


# sub-long vAA, vBB, vCC ( 8b, 8b, 8b )


# mul-long vAA, vBB, vCC ( 8b, 8b, 8b )


# div-long vAA, vBB, vCC ( 8b, 8b, 8b )


# rem-long vAA, vBB, vCC ( 8b, 8b, 8b )


# and-long vAA, vBB, vCC ( 8b, 8b, 8b )


# or-long vAA, vBB, vCC ( 8b, 8b, 8b )


# xor-long vAA, vBB, vCC ( 8b, 8b, 8b )


# shl-long vAA, vBB, vCC ( 8b, 8b, 8b )


# shr-long vAA, vBB, vCC ( 8b, 8b, 8b )


# ushr-long vAA, vBB, vCC ( 8b, 8b, 8b )


# add-float vAA, vBB, vCC ( 8b, 8b, 8b )


# sub-float vAA, vBB, vCC ( 8b, 8b, 8b )


# mul-float vAA, vBB, vCC ( 8b, 8b, 8b )


# div-float vAA, vBB, vCC ( 8b, 8b, 8b )


# rem-float vAA, vBB, vCC ( 8b, 8b, 8b )


# add-double vAA, vBB, vCC ( 8b, 8b, 8b )


# sub-double vAA, vBB, vCC ( 8b, 8b, 8b )


# mul-double vAA, vBB, vCC ( 8b, 8b, 8b )


# div-double vAA, vBB, vCC ( 8b, 8b, 8b )


# rem-double vAA, vBB, vCC ( 8b, 8b, 8b )


# add-int/2addr vA, vB ( 4b, 4b )


# sub-int/2addr vA, vB ( 4b, 4b )


# mul-int/2addr vA, vB ( 4b, 4b )


# div-int/2addr vA, vB ( 4b, 4b )


# rem-int/2addr vA, vB ( 4b, 4b )


# and-int/2addr vA, vB ( 4b, 4b )


# or-int/2addr vA, vB ( 4b, 4b )


# xor-int/2addr vA, vB ( 4b, 4b )


# shl-int/2addr vA, vB ( 4b, 4b )


# shr-int/2addr vA, vB ( 4b, 4b )


# ushr-int/2addr vA, vB ( 4b, 4b )


# add-long/2addr vA, vB ( 4b, 4b )


# sub-long/2addr vA, vB ( 4b, 4b )


# mul-long/2addr vA, vB ( 4b, 4b )


# div-long/2addr vA, vB ( 4b, 4b )


# rem-long/2addr vA, vB ( 4b, 4b )


# and-long/2addr vA, vB ( 4b, 4b )


# or-long/2addr vA, vB ( 4b, 4b )


# xor-long/2addr vA, vB ( 4b, 4b )


# shl-long/2addr vA, vB ( 4b, 4b )


# shr-long/2addr vA, vB ( 4b, 4b )


# ushr-long/2addr vA, vB ( 4b, 4b )


# add-float/2addr vA, vB ( 4b, 4b )


# sub-float/2addr vA, vB ( 4b, 4b )


# mul-float/2addr vA, vB ( 4b, 4b )


# div-float/2addr vA, vB ( 4b, 4b )


# rem-float/2addr vA, vB ( 4b, 4b )


# add-double/2addr vA, vB ( 4b, 4b )


# sub-double/2addr vA, vB ( 4b, 4b )


# mul-double/2addr vA, vB ( 4b, 4b )


# div-double/2addr vA, vB ( 4b, 4b )


# rem-double/2addr vA, vB ( 4b, 4b )


# add-int/lit16 vA, vB, #+CCCC ( 4b, 4b, 16b )


# rsub-int vA, vB, #+CCCC ( 4b, 4b, 16b )


# mul-int/lit16 vA, vB, #+CCCC ( 4b, 4b, 16b )


# div-int/lit16 vA, vB, #+CCCC ( 4b, 4b, 16b )


# rem-int/lit16 vA, vB, #+CCCC ( 4b, 4b, 16b )


# and-int/lit16 vA, vB, #+CCCC ( 4b, 4b, 16b )


# or-int/lit16 vA, vB, #+CCCC ( 4b, 4b, 16b )


# xor-int/lit16 vA, vB, #+CCCC ( 4b, 4b, 16b )


# add-int/lit8 vAA, vBB, #+CC ( 8b, 8b, 8b )


# rsub-int/lit8 vAA, vBB, #+CC ( 8b, 8b, 8b )


# mul-int/lit8 vAA, vBB, #+CC ( 8b, 8b, 8b )


# div-int/lit8 vAA, vBB, #+CC ( 8b, 8b, 8b )


# rem-int/lit8 vAA, vBB, #+CC ( 8b, 8b, 8b )


# and-int/lit8 vAA, vBB, #+CC ( 8b, 8b, 8b )


# or-int/lit8 vAA, vBB, #+CC ( 8b, 8b, 8b )


# xor-int/lit8 vAA, vBB, #+CC ( 8b, 8b, 8b )


# shl-int/lit8 vAA, vBB, #+CC ( 8b, 8b, 8b )


# shr-int/lit8 vAA, vBB, #+CC ( 8b, 8b, 8b )


# ushr-int/lit8 vAA, vBB, #+CC ( 8b, 8b, 8b )


# FIXME: Need to add all opcodes here, check for new unused ones.
# FIXME: The instruction set is dalvik version specific
INSTRUCTION_SET = [
    # 0x00
    nop,  # nop
    move,  # move
    movefrom16,  # move/from16
    move16,  # move/16
    movewide,  # move-wide
    movewidefrom16,  # move-wide/from16
    movewide16,  # move-wide/16
    moveobject,  # move-object
    moveobjectfrom16,  # move-object/from16
    moveobject16,  # move-object/16
    moveresult,  # move-result
    moveresultwide,  # move-result-wide
    moveresultobject,  # move-result-object
    moveexception,  # move-exception
    returnvoid,  # return-void
    return_reg,  # return
    # 0x10
    returnwide,  # return-wide
    returnobject,  # return-object
    const4,  # const/4
    const16,  # const/16
    const,  # const
    consthigh16,  # const/high16
    constwide16,  # const-wide/16
    constwide32,  # const-wide/32
    constwide,  # const-wide
    constwidehigh16,  # const-wide/high16
    conststring,  # const-string
    conststringjumbo,  # const-string/jumbo
    constclass,  # const-class
    monitorenter,  # monitor-enter
    monitorexit,  # monitor-exit
    checkcast,  # check-cast
    # 0x20
    instanceof,  # instance-of
    arraylength,  # array-length
    newinstance,  # new-instance
    newarray,  # new-array
    fillednewarray,  # filled-new-array
    fillednewarrayrange,  # filled-new-array/range
    fillarraydata,  # fill-array-data
    throw,  # throw
    goto,  # goto
    goto16,  # goto/16
    goto32,  # goto/32
    packedswitch,  # packed-switch
    sparseswitch,  # sparse-switch
    cmplfloat,  # cmpl-float
    cmpgfloat,  # cmpg-float
    cmpldouble,  # cmpl-double
    # 0x30
    cmpgdouble,  # cmpg-double
    cmplong,  # cmp-long
    ifeq,  # if-eq
    ifne,  # if-ne
    iflt,  # if-lt
    ifge,  # if-ge
    ifgt,  # if-gt
    ifle,  # if-le
    ifeqz,  # if-eqz
    ifnez,  # if-nez
    ifltz,  # if-ltz
    ifgez,  # if-gez
    ifgtz,  # if-gtz
    iflez,  # if-l
    nop,  # unused
    nop,  # unused
    # 0x40
    nop,  # unused
    nop,  # unused
    nop,  # unused
    nop,  # unused
    aget,  # aget
    agetwide,  # aget-wide
    agetobject,  # aget-object
    agetboolean,  # aget-boolean
    agetbyte,  # aget-byte
    agetchar,  # aget-char
    agetshort,  # aget-short
    aput,  # aput
    aputwide,  # aput-wide
    aputobject,  # aput-object
    aputboolean,  # aput-boolean
    aputbyte,  # aput-byte
    # 0x50
    aputchar,  # aput-char
    aputshort,  # aput-short
    iget,  # iget
    igetwide,  # iget-wide
    igetobject,  # iget-object
    igetboolean,  # iget-boolean
    igetbyte,  # iget-byte
    igetchar,  # iget-char
    igetshort,  # iget-short
    iput,  # iput
    iputwide,  # iput-wide
    iputobject,  # iput-object
    iputboolean,  # iput-boolean
    iputbyte,  # iput-byte
    iputchar,  # iput-char
    iputshort,  # iput-short
    # 0x60
    sget,  # sget
    sgetwide,  # sget-wide
    sgetobject,  # sget-object
    sgetboolean,  # sget-boolean
    sgetbyte,  # sget-byte
    sgetchar,  # sget-char
    sgetshort,  # sget-short
    sput,  # sput
    sputwide,  # sput-wide
    sputobject,  # sput-object
    sputboolean,  # sput-boolean
    sputbyte,  # sput-byte
    sputchar,  # sput-char
    sputshort,  # sput-short
    invokevirtual,  # invoke-virtual
    invokesuper,  # invoke-super
    # 0x70
    invokedirect,  # invoke-direct
    invokestatic,  # invoke-static
    invokeinterface,  # invoke-interface
    nop,  # unused
    invokevirtualrange,  # invoke-virtual/range
    invokesuperrange,  # invoke-super/range
    invokedirectrange,  # invoke-direct/range
    invokestaticrange,  # invoke-static/range
    invokeinterfacerange,  # invoke-interface/range
    nop,  # unused
    nop,  # unused
    negint,  # neg-int
    notint,  # not-int
    neglong,  # neg-long
    notlong,  # not-long
    negfloat,  # neg-float
    # 0x80
    negdouble,  # neg-double
    inttolong,  # int-to-long
    inttofloat,  # int-to-float
    inttodouble,  # int-to-double
    longtoint,  # long-to-int
    longtofloat,  # long-to-float
    longtodouble,  # long-to-double
    floattoint,  # float-to-int
    floattolong,  # float-to-long
    floattodouble,  # float-to-double
    doubletoint,  # double-to-int
    doubletolong,  # double-to-long
    doubletofloat,  # double-to-float
    inttobyte,  # int-to-byte
    inttochar,  # int-to-char
    inttoshort,  # int-to-short
    # 0x90
    addint,  # add-int
    subint,  # sub-int
    mulint,  # mul-int
    divint,  # div-int
    remint,  # rem-int
    andint,  # and-int
    orint,  # or-int
    xorint,  # xor-int
    shlint,  # shl-int
    shrint,  # shr-int
    ushrint,  # ushr-int
    addlong,  # add-long
    sublong,  # sub-long
    mullong,  # mul-long
    divlong,  # div-long
    remlong,  # rem-long
    # 0xa0
    andlong,  # and-long
    orlong,  # or-long
    xorlong,  # xor-long
    shllong,  # shl-long
    shrlong,  # shr-long
    ushrlong,  # ushr-long
    addfloat,  # add-float
    subfloat,  # sub-float
    mulfloat,  # mul-float
    divfloat,  # div-float
    remfloat,  # rem-float
    adddouble,  # add-double
    subdouble,  # sub-double
    muldouble,  # mul-double
    divdouble,  # div-double
    remdouble,  # rem-double
    # 0xb0
    addint2addr,  # add-int/2addr
    subint2addr,  # sub-int/2addr
    mulint2addr,  # mul-int/2addr
    divint2addr,  # div-int/2addr
    remint2addr,  # rem-int/2addr
    andint2addr,  # and-int/2addr
    orint2addr,  # or-int/2addr
    xorint2addr,  # xor-int/2addr
    shlint2addr,  # shl-int/2addr
    shrint2addr,  # shr-int/2addr
    ushrint2addr,  # ushr-int/2addr
    addlong2addr,  # add-long/2addr
    sublong2addr,  # sub-long/2addr
    mullong2addr,  # mul-long/2addr
    divlong2addr,  # div-long/2addr
    remlong2addr,  # rem-long/2addr
    # 0xc0
    andlong2addr,  # and-long/2addr
    orlong2addr,  # or-long/2addr
    xorlong2addr,  # xor-long/2addr
    shllong2addr,  # shl-long/2addr
    shrlong2addr,  # shr-long/2addr
    ushrlong2addr,  # ushr-long/2addr
    addfloat2addr,  # add-float/2addr
    subfloat2addr,  # sub-float/2addr
    mulfloat2addr,  # mul-float/2addr
    divfloat2addr,  # div-float/2addr
    remfloat2addr,  # rem-float/2addr
    adddouble2addr,  # add-double/2addr
    subdouble2addr,  # sub-double/2addr
    muldouble2addr,  # mul-double/2addr
    divdouble2addr,  # div-double/2addr
    remdouble2addr,  # rem-double/2addr
    # 0xd0
    addintlit16,  # add-int/lit16
    rsubint,  # rsub-int
    mulintlit16,  # mul-int/lit16
    divintlit16,  # div-int/lit16
    remintlit16,  # rem-int/lit16
    andintlit16,  # and-int/lit16
    orintlit16,  # or-int/lit16
    xorintlit16,  # xor-int/lit16
    addintlit8,  # add-int/lit8
    rsubintlit8,  # rsub-int/lit8
    mulintlit8,  # mul-int/lit8
    divintlit8,  # div-int/lit8
    remintlit8,  # rem-int/lit8
    andintlit8,  # and-int/lit8
    orintlit8,  # or-int/lit8
    xorintlit8,  # xor-int/lit8
    # 0xe0
    shlintlit8,  # shl-int/lit8
    shrintlit8,  # shr-int/lit8
    ushrintlit8,  # ushr-int/lit8
]
