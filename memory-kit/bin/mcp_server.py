#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memory-kit :: mcp_server.py —— MCP stdio 服务器（agent 用）
工具：search_memory / recent_logs / clusters / kit_about
      create_memory_session / append_memory_turn / session_history
      memory_context / get_memory_context
运行：python mcp_server.py   （由 MCP 客户端以 stdio 方式拉起）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kitcore import KitIndex, KIT  # noqa: E402
from memory_service import MemoryService  # noqa: E402

try:
    from mcp.server.fastmcp import FastMCP as MCPServer  # mcp 1.x
except ImportError:  # mcp 2.x: FastMCP 改名 MCPServer，接口兼容
    from mcp.server.mcpserver import MCPServer

mcp = MCPServer('memory-kit')
INDEX = KitIndex().load()
SERVICE = MemoryService(INDEX, KIT, INDEX.cfg)


@mcp.tool()
def search_memory(query: str, k: int = 8, mode: str = 'hybrid',
                  date_from: str = '', date_to: str = '', machine: str = '',
                  topic: str = '') -> dict:
    """在随身日志记忆库中混合检索（语义+关键词，RRF 融合）。
    query: 自然语言查询；k: 返回条数；mode: hybrid/dense/sparse；
    date_from/date_to: 可选 YYYY-MM-DD 过滤；machine/topic: 可选过滤。
    返回每条含 topic/date/preview/source。"""
    return SERVICE.search({
        'query': query,
        'k': k,
        'mode': mode,
        'machine': machine,
        'date_from': date_from,
        'date_to': date_to,
        'topic': topic,
    }, protocol='mcp')


@mcp.tool()
def recent_logs(days: int = 3, k: int = 20) -> dict:
    """最近 N 天的日志块（按日期倒序）。返回 id/date/topic/source/preview。"""
    return {'days': days, 'results': INDEX.recent(days, k)}


@mcp.tool()
def clusters() -> dict:
    """当前记忆库的自动整理结果：社区列表（规模/主题/关键词/日期范围）。"""
    return INDEX.cluster_info() or {'clusters': []}


@mcp.tool()
def kit_about() -> dict:
    """记忆库概况：kit 根路径、块数、向量数、生成时间。"""
    return {
        'kit_root': KIT,
        'chunks': len(INDEX.chunks),
        'vectors': INDEX.n,
        'organized_at': (INDEX.org or {}).get('generated_at'),
        'machines': sorted({m for c in INDEX.chunks for m in c['machines']}),
        'memory': SERVICE.stats(),
    }


@mcp.tool()
def create_memory_session(owner: str = 'default', title: str = '') -> dict:
    """创建工作记忆会话。owner 用于隔离不同 agent/用户，title 为可读标题。"""
    return SERVICE.create_session({'owner': owner, 'title': title})


@mcp.tool()
def append_memory_turn(session_id: str, role: str, content: str,
                       owner: str = 'default') -> dict:
    """向工作记忆会话追加一轮，role 支持 system/user/assistant/tool。
    会话按 owner 隔离、按条数截断，并按 TTL 自动过期。"""
    return SERVICE.append_turn(owner, session_id, {'role': role, 'content': content})


@mcp.tool()
def session_history(session_id: str, owner: str = 'default') -> dict:
    """读取一个工作记忆会话的完整有界历史。"""
    return SERVICE.get_session(owner, session_id)


@mcp.tool()
def memory_context(query: str, owner: str = 'default', session_id: str = '',
                   k: int = 8, mode: str = 'hybrid', max_chars: int = 6000) -> dict:
    """生成 MEMORY_CONTEXT 上下文包：工作记忆 + 长期日志检索命中。
    结果有 TTL、按 owner 隔离，并返回 context_id 供后续读取。"""
    return SERVICE.build_context({
        'owner': owner,
        'session_id': session_id or None,
        'query': query,
        'k': k,
        'mode': mode,
        'max_chars': max_chars,
    })


@mcp.tool()
def get_memory_context(context_id: str, owner: str = 'default') -> dict:
    """读取未过期的 MEMORY_CONTEXT；跨 owner 不可见。"""
    return SERVICE.get_context(owner, context_id)


if __name__ == '__main__':
    mcp.run()
