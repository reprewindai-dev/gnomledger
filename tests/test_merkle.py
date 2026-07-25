import pytest
from backend.app.services.merkle_service import MerkleTree, hash_leaf, verify_merkle_proof

def test_merkle_tree_generation():
    leaves = ["event1", "event2", "event3", "event4"]
    tree = MerkleTree(leaves)
    root = tree.get_root()
    assert root is not None
    assert len(root) == 64  # SHA-256 hash length

def test_merkle_proof_verification():
    leaves = ["event1", "event2", "event3", "event4"]
    tree = MerkleTree(leaves)
    root = tree.get_root()
    
    # Test valid proof for leaf 1
    proof = tree.get_proof(1)
    is_valid = verify_merkle_proof("event2", proof, root)
    assert is_valid == True
    
    # Test invalid proof (tampered data)
    is_valid_tampered = verify_merkle_proof("event2_tampered", proof, root)
    assert is_valid_tampered == False

def test_merkle_tree_odd_leaves():
    leaves = ["event1", "event2", "event3"]
    tree = MerkleTree(leaves)
    root = tree.get_root()
    
    # Proof for the 3rd leaf
    proof = tree.get_proof(2)
    assert verify_merkle_proof("event3", proof, root) == True
