"""
Test script for assembler.py
Run with: python test_assembler.py
"""


import sys
from pathlib import Path

# Add parent directory to path to allow imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from datetime import datetime
from uuid import uuid4  
from workers.anonymization.pipeline.assembler import assemble_anonymized, ANONYMIZATION_VERSION


def test_basic_assembly():
    print("\n" + "="*60)
    print("TEST 1: Basic successful assembly")
    print("="*60)
    
    session_id = uuid4()
    normalized_at = datetime(2024, 1, 15, 10, 30, 0)
    anonymized_at = datetime(2024, 1, 15, 10, 35, 0)
    
    normalized = {
        "signals": {"language": "en", "job_title": "Engineer"},
        "metrics": {"word_count": 500, "section_count": 5},
        "timestamps": {
            "normalized_at": normalized_at.isoformat()
        }
    }
    
    redacted_blocks = {
        "main": [
            {"text": "Contact me at {{EMAIL_1}}", "source_span": {"start": 0, "end": 25}}
        ]
    }
    
    redactions = {
        "emails": [{"placeholder": "{{EMAIL_1}}", "original_span": {"start": 14, "end": 31}}],
        "phones": [],
        "urls": []
    }
    
    result = assemble_anonymized(
        session_id=session_id,
        normalized=normalized,
        redacted_blocks=redacted_blocks,
        redactions=redactions,
        anonymized_at=anonymized_at
    )
    
    # Verify structure
    assert result["session_id"] == str(session_id)
    assert result["anonymization_version"] == ANONYMIZATION_VERSION
    assert result["content"]["blocks"] == redacted_blocks
    assert result["redactions"] == redactions
    assert result["signals"] == normalized["signals"]
    assert result["metrics"] == normalized["metrics"]
    assert result["timestamps"]["normalized_at"] == normalized_at.isoformat()
    assert result["timestamps"]["anonymized_at"] == anonymized_at.isoformat()
    
    print("✓ Session ID matches")
    print("✓ Version matches")
    print("✓ Content blocks preserved")
    print("✓ Redactions preserved")
    print("✓ Signals preserved")
    print("✓ Metrics preserved")
    print("✓ Timestamps correct")
    print("✓ PASS")


def test_session_id_as_string():
    print("\n" + "="*60)
    print("TEST 2: Session ID as string (not UUID)")
    print("="*60)
    
    session_id = "custom-session-123"
    anonymized_at = datetime.now()
    
    normalized = {
        "signals": {},
        "metrics": {},
        "timestamps": {"normalized_at": "2024-01-15T10:30:00"}
    }
    
    result = assemble_anonymized(
        session_id=session_id,
        normalized=normalized,
        redacted_blocks={},
        redactions={"emails": [], "phones": [], "urls": []},
        anonymized_at=anonymized_at
    )
    
    assert result["session_id"] == session_id
    print(f"✓ String session ID works: {session_id}")
    print("✓ PASS")


def test_missing_signals():
    print("\n" + "="*60)
    print("TEST 3: Missing signals (should raise error)")
    print("="*60)
    
    normalized = {
        "metrics": {},
        "timestamps": {"normalized_at": "2024-01-15T10:30:00"}
        # Missing "signals"
    }
    
    try:
        assemble_anonymized(
            session_id="test",
            normalized=normalized,
            redacted_blocks={},
            redactions={},
            anonymized_at=datetime.now()
        )
        print("✗ FAIL - Should have raised error")
        assert False, "Should have raised PermanentAnonymizationError"
    except Exception as e:
        assert "missing signals or metrics" in str(e)
        print(f"✓ Correctly raised error: {e}")
        print("✓ PASS")


def test_missing_metrics():
    print("\n" + "="*60)
    print("TEST 4: Missing metrics (should raise error)")
    print("="*60)
    
    normalized = {
        "signals": {},
        "timestamps": {"normalized_at": "2024-01-15T10:30:00"}
        # Missing "metrics"
    }
    
    try:
        assemble_anonymized(
            session_id="test",
            normalized=normalized,
            redacted_blocks={},
            redactions={},
            anonymized_at=datetime.now()
        )
        print("✗ FAIL - Should have raised error")
        assert False, "Should have raised PermanentAnonymizationError"
    except Exception as e:
        assert "missing signals or metrics" in str(e)
        print(f"✓ Correctly raised error: {e}")
        print("✓ PASS")


def test_normalized_not_dict():
    print("\n" + "="*60)
    print("TEST 5: Normalized is not a dict (should raise error)")
    print("="*60)
    
    try:
        assemble_anonymized(
            session_id="test",
            normalized="not a dict",
            redacted_blocks={},
            redactions={},
            anonymized_at=datetime.now()
        )
        print("✗ FAIL - Should have raised error")
        assert False, "Should have raised PermanentAnonymizationError"
    except Exception as e:
        assert "must be a dict" in str(e)
        print(f"✓ Correctly raised error: {e}")
        print("✓ PASS")


def test_missing_timestamps():
    print("\n" + "="*60)
    print("TEST 6: Missing timestamps (should raise error)")
    print("="*60)
    
    normalized = {
        "signals": {},
        "metrics": {}
        # Missing "timestamps"
    }
    
    try:
        assemble_anonymized(
            session_id="test",
            normalized=normalized,
            redacted_blocks={},
            redactions={},
            anonymized_at=datetime.now()
        )
        print("✗ FAIL - Should have raised error")
        assert False, "Should have raised PermanentAnonymizationError"
    except Exception as e:
        assert "missing timestamps" in str(e)
        print(f"✓ Correctly raised error: {e}")
        print("✓ PASS")


def test_missing_normalized_at():
    print("\n" + "="*60)
    print("TEST 7: Missing normalized_at in timestamps (should raise error)")
    print("="*60)
    
    normalized = {
        "signals": {},
        "metrics": {},
        "timestamps": {}  # Missing "normalized_at"
    }
    
    try:
        assemble_anonymized(
            session_id="test",
            normalized=normalized,
            redacted_blocks={},
            redactions={},
            anonymized_at=datetime.now()
        )
        print("✗ FAIL - Should have raised error")
        assert False, "Should have raised PermanentAnonymizationError"
    except Exception as e:
        assert "missing normalized_at" in str(e)
        print(f"✓ Correctly raised error: {e}")
        print("✓ PASS")


def test_complete_realistic_data():
    print("\n" + "="*60)
    print("TEST 8: Complete realistic data structure")
    print("="*60)
    
    session_id = uuid4()
    normalized_at = datetime(2024, 1, 15, 10, 30, 0)
    anonymized_at = datetime(2024, 1, 15, 10, 35, 0)
    
    normalized = {
        "signals": {
            "language": "en",
            "job_title": "Software Engineer",
            "years_experience": 5,
            "skills": ["Python", "JavaScript", "SQL"]
        },
        "metrics": {
            "word_count": 1250,
            "section_count": 8,
            "bullet_count": 25,
            "email_count": 2,
            "phone_count": 1,
            "url_count": 3
        },
        "timestamps": {
            "normalized_at": normalized_at.isoformat(),
            "parsed_at": "2024-01-15T10:25:00"
        }
    }
    
    redacted_blocks = {
        "header": [
            {
                "text": "{{EMAIL_1}} | {{PHONE_1}}",
                "source_span": {"start": 0, "end": 50}
            }
        ],
        "experience": [
            {
                "text": "Worked at Acme Corp. See {{URL_1}}",
                "source_span": {"start": 100, "end": 150}
            }
        ]
    }
    
    redactions = {
        "emails": [
            {"placeholder": "{{EMAIL_1}}", "original_span": {"start": 0, "end": 17}},
            {"placeholder": "{{EMAIL_2}}", "original_span": {"start": 200, "end": 215}}
        ],
        "phones": [
            {"placeholder": "{{PHONE_1}}", "original_span": {"start": 20, "end": 32}}
        ],
        "urls": [
            {"placeholder": "{{URL_1}}", "original_span": {"start": 130, "end": 150}},
            {"placeholder": "{{URL_2}}", "original_span": {"start": 300, "end": 325}},
            {"placeholder": "{{URL_3}}", "original_span": {"start": 400, "end": 430}}
        ]
    }
    
    result = assemble_anonymized(
        session_id=session_id,
        normalized=normalized,
        redacted_blocks=redacted_blocks,
        redactions=redactions,
        anonymized_at=anonymized_at
    )
    
    # Detailed verification
    assert result["session_id"] == str(session_id)
    assert result["anonymization_version"] == "1.0"
    
    # Check nested structure
    assert "header" in result["content"]["blocks"]
    assert "experience" in result["content"]["blocks"]
    assert len(result["content"]["blocks"]["header"]) == 1
    assert len(result["content"]["blocks"]["experience"]) == 1
    
    # Check redactions
    assert len(result["redactions"]["emails"]) == 2
    assert len(result["redactions"]["phones"]) == 1
    assert len(result["redactions"]["urls"]) == 3
    
    # Check signals preserved
    assert result["signals"]["language"] == "en"
    assert result["signals"]["job_title"] == "Software Engineer"
    assert len(result["signals"]["skills"]) == 3
    
    # Check metrics preserved
    assert result["metrics"]["word_count"] == 1250
    assert result["metrics"]["email_count"] == 2
    
    # Check timestamps
    assert result["timestamps"]["normalized_at"] == normalized_at.isoformat()
    assert result["timestamps"]["anonymized_at"] == anonymized_at.isoformat()
    
    print("✓ All structure validated")
    print("✓ All nested data preserved")
    print("✓ All counts match")
    print("✓ PASS")


if __name__ == "__main__":
    print("\n🧪 RUNNING ASSEMBLER TESTS\n")
    
    try:
        test_basic_assembly()
        test_session_id_as_string()
        test_missing_signals()
        test_missing_metrics()
        test_normalized_not_dict()
        test_missing_timestamps()
        test_missing_normalized_at()
        test_complete_realistic_data()
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED")
        print("="*60 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        raise
    except Exception as e:
        print(f"\n💥 UNEXPECTED ERROR: {e}\n")
        raise