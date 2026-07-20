import hashlib
from typing import List, Optional

def hash_node(left: str, right: str) -> str:
    """Hash two node strings together using SHA-256."""
    combined = (left + right).encode("utf-8")
    return hashlib.sha256(combined).hexdigest()

def hash_leaf(data: str) -> str:
    """Hash a leaf node data string."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()

class MerkleTree:
    def __init__(self, leaves: List[str]):
        if not leaves:
            raise ValueError("Cannot create a Merkle tree without leaves")
        self.leaves = [hash_leaf(leaf) for leaf in leaves]
        self.tree = self._build_tree(self.leaves)

    def _build_tree(self, nodes: List[str]) -> List[List[str]]:
        tree = [nodes]
        current_level = nodes
        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else current_level[i]
                next_level.append(hash_node(left, right))
            tree.append(next_level)
            current_level = next_level
        return tree

    def get_root(self) -> str:
        """Returns the Merkle root hash."""
        return self.tree[-1][0]

    def get_proof(self, index: int) -> List[dict[str, str]]:
        """
        Returns the Merkle proof for a leaf at the given index.
        The proof is a list of dicts with 'position' ('left' or 'right') and 'hash'.
        """
        if index < 0 or index >= len(self.leaves):
            raise IndexError("Leaf index out of bounds")

        proof = []
        current_index = index

        for level in range(len(self.tree) - 1):
            level_nodes = self.tree[level]
            is_right_node = current_index % 2 == 1
            
            if is_right_node:
                sibling_index = current_index - 1
                sibling_pos = "left"
            else:
                sibling_index = current_index + 1
                sibling_pos = "right"
                
                if sibling_index >= len(level_nodes):
                    sibling_index = current_index
            
            proof.append({
                "position": sibling_pos,
                "hash": level_nodes[sibling_index]
            })
            
            current_index //= 2

        return proof

def verify_merkle_proof(leaf: str, proof: List[dict[str, str]], root: str) -> bool:
    """
    Verifies a Merkle proof for a given leaf.
    """
    current_hash = hash_leaf(leaf)
    
    for step in proof:
        if step["position"] == "left":
            current_hash = hash_node(step["hash"], current_hash)
        else:
            current_hash = hash_node(current_hash, step["hash"])
            
    return current_hash == root
