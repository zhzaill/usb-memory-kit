#!/usr/bin/env python3
import json
import os
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(KIT, 'index')


def read_ids(path):
    ids = []
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as handle:
            for line in handle:
                if line.strip():
                    ids.append(json.loads(line)['id'])
    return ids


def main():
    chunks = read_ids(os.path.join(INDEX, 'chunks.jsonl'))
    vectors = read_ids(os.path.join(INDEX, 'vectors.jsonl'))
    chunk_ids, vector_ids = set(chunks), set(vectors)
    result = {
        'chunks': len(chunks),
        'vectors': len(vectors),
        'missing': len(chunk_ids - vector_ids),
        'orphan_vectors': len(vector_ids - chunk_ids),
        'duplicate_chunks': len(chunks) - len(chunk_ids),
        'duplicate_vectors': len(vectors) - len(vector_ids),
        'complete': chunk_ids == vector_ids and len(chunks) == len(chunk_ids) and len(vectors) == len(vector_ids),
    }
    print(json.dumps(result, ensure_ascii=False))
    if '--strict' in sys.argv and not result['complete']:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
