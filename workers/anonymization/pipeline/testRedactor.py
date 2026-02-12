"""
Test script for redactor.py

Run with: python test_redactor.py
"""

from redactor import redact_content

def test_basic_single_email():
    print("\n" + "="*60)
    print("TEST 1: Basic single email redaction")
    print("="*60)
    
    blocks = {
        "main": [
            {
                "text": "Contact me at alice@example.com for details",
                "source_span": {"start": 0, "end": 43}
            }
        ]
    }
    
    entities = {
        "emails": [
            {"value": "alice@example.com", "span": {"start": 14, "end": 31}}
        ]
    }
    
    redacted, records = redact_content(blocks=blocks, entities=entities)
    
    result = redacted["main"][0]["text"]
    expected = "Contact me at {{EMAIL_1}} for details"
    
    print(f"Input:    '{blocks['main'][0]['text']}'")
    print(f"Output:   '{result}'")
    print(f"Expected: '{expected}'")
    print(f"✓ PASS" if result == expected else f"✗ FAIL")
    
    assert result == expected, f"Expected '{expected}', got '{result}'"
    assert len(records["emails"]) == 1
    assert records["emails"][0]["placeholder"] == "{{EMAIL_1}}"
    print(f"Records: {records['emails']}")


def test_multiple_entities_same_block():
    print("\n" + "="*60)
    print("TEST 2: Multiple entities in same block")
    print("="*60)
    
    blocks = {
        "main": [
            {
                "text": "Email alice@example.com or call 555-1234",
                "source_span": {"start": 0, "end": 41}
            }
        ]
    }
    
    entities = {
        "emails": [
            {"value": "alice@example.com", "span": {"start": 6, "end": 23}}
        ],
        "phones": [
            {"value": "555-1234", "span": {"start": 32, "end": 41}}
        ]
    }
    
    redacted, records = redact_content(blocks=blocks, entities=entities)
    
    result = redacted["main"][0]["text"]
    expected = "Email {{EMAIL_1}} or call {{PHONE_1}}"
    
    print(f"Input:    '{blocks['main'][0]['text']}'")
    print(f"Output:   '{result}'")
    print(f"Expected: '{expected}'")
    print(f"✓ PASS" if result == expected else f"✗ FAIL")
    
    assert result == expected, f"Expected '{expected}', got '{result}'"
    assert len(records["emails"]) == 1
    assert len(records["phones"]) == 1


def test_multiple_blocks():
    print("\n" + "="*60)
    print("TEST 3: Multiple blocks")
    print("="*60)
    
    blocks = {
        "main": [
            {
                "text": "First email: alice@example.com",
                "source_span": {"start": 0, "end": 30}
            },
            {
                "text": "Second email: bob@example.com",
                "source_span": {"start": 31, "end": 60}
            }
        ]
    }
    
    entities = {
        "emails": [
            {"value": "alice@example.com", "span": {"start": 13, "end": 30}},
            {"value": "bob@example.com", "span": {"start": 45, "end": 60}}
        ]
    }
    
    redacted, records = redact_content(blocks=blocks, entities=entities)
    
    result1 = redacted["main"][0]["text"]
    result2 = redacted["main"][1]["text"]
    expected1 = "First email: {{EMAIL_1}}"
    expected2 = "Second email: {{EMAIL_2}}"
    
    print(f"Block 1 Input:    '{blocks['main'][0]['text']}'")
    print(f"Block 1 Output:   '{result1}'")
    print(f"Block 1 Expected: '{expected1}'")
    print(f"Block 1: {'✓ PASS' if result1 == expected1 else '✗ FAIL'}")
    
    print(f"\nBlock 2 Input:    '{blocks['main'][1]['text']}'")
    print(f"Block 2 Output:   '{result2}'")
    print(f"Block 2 Expected: '{expected2}'")
    print(f"Block 2: {'✓ PASS' if result2 == expected2 else '✗ FAIL'}")
    
    assert result1 == expected1
    assert result2 == expected2
    assert len(records["emails"]) == 2


def test_same_value_multiple_times():
    print("\n" + "="*60)
    print("TEST 4: Same email appears twice (should use same placeholder)")
    print("="*60)
    
    blocks = {
        "main": [
            {
                "text": "Email alice@example.com and again alice@example.com",
                "source_span": {"start": 0, "end": 52}
            }
        ]
    }
    
    entities = {
        "emails": [
            {"value": "alice@example.com", "span": {"start": 6, "end": 23}},
            {"value": "alice@example.com", "span": {"start": 34, "end": 52}}
        ]
    }
    
    redacted, records = redact_content(blocks=blocks, entities=entities)
    
    result = redacted["main"][0]["text"]
    expected = "Email {{EMAIL_1}} and again {{EMAIL_1}}"
    
    print(f"Input:    '{blocks['main'][0]['text']}'")
    print(f"Output:   '{result}'")
    print(f"Expected: '{expected}'")
    print(f"✓ PASS" if result == expected else f"✗ FAIL")
    
    assert result == expected
    # Should have 2 records (one per occurrence)
    assert len(records["emails"]) == 2
    # Both should use same placeholder
    assert records["emails"][0]["placeholder"] == "{{EMAIL_1}}"
    assert records["emails"][1]["placeholder"] == "{{EMAIL_1}}"


def test_no_entities():
    print("\n" + "="*60)
    print("TEST 5: No entities to redact")
    print("="*60)
    
    blocks = {
        "main": [
            {
                "text": "Just some plain text",
                "source_span": {"start": 0, "end": 20}
            }
        ]
    }
    
    entities = {
        "emails": [],
        "phones": [],
        "urls": []
    }
    
    redacted, records = redact_content(blocks=blocks, entities=entities)
    
    result = redacted["main"][0]["text"]
    expected = "Just some plain text"
    
    print(f"Input:    '{blocks['main'][0]['text']}'")
    print(f"Output:   '{result}'")
    print(f"Expected: '{expected}'")
    print(f"✓ PASS" if result == expected else f"✗ FAIL")
    
    assert result == expected
    assert len(records["emails"]) == 0
    assert len(records["phones"]) == 0


def test_right_to_left_order():
    print("\n" + "="*60)
    print("TEST 6: Right-to-left replacement order (critical)")
    print("="*60)
    
    blocks = {
        "main": [
            {
                "text": "abc123def456ghi",
                "source_span": {"start": 0, "end": 15}
            }
        ]
    }
    
    entities = {
        "phones": [
            {"value": "123", "span": {"start": 3, "end": 6}},
            {"value": "456", "span": {"start": 9, "end": 12}}
        ]
    }
    
    redacted, records = redact_content(blocks=blocks, entities=entities)
    
    result = redacted["main"][0]["text"]
    expected = "abc{{PHONE_1}}def{{PHONE_2}}ghi"
    
    print(f"Input:    '{blocks['main'][0]['text']}'")
    print(f"Output:   '{result}'")
    print(f"Expected: '{expected}'")
    print(f"✓ PASS" if result == expected else f"✗ FAIL")
    
    assert result == expected, f"Expected '{expected}', got '{result}'"


def test_entity_not_in_block():
    print("\n" + "="*60)
    print("TEST 7: Entity span outside block range")
    print("="*60)
    
    blocks = {
        "main": [
            {
                "text": "Just this block",
                "source_span": {"start": 0, "end": 15}
            }
        ]
    }
    
    entities = {
        "emails": [
            # This entity is outside the block's span
            {"value": "alice@example.com", "span": {"start": 100, "end": 117}}
        ]
    }
    
    redacted, records = redact_content(blocks=blocks, entities=entities)
    
    result = redacted["main"][0]["text"]
    expected = "Just this block"  # Should be unchanged
    
    print(f"Input:    '{blocks['main'][0]['text']}'")
    print(f"Output:   '{result}'")
    print(f"Expected: '{expected}'")
    print(f"✓ PASS" if result == expected else f"✗ FAIL")
    
    assert result == expected
    assert len(records["emails"]) == 0


if __name__ == "__main__":
    print("\n" + "🧪 RUNNING REDACTOR TESTS" + "\n")
    
    try:
        test_basic_single_email()
        test_multiple_entities_same_block()
        test_multiple_blocks()
        test_same_value_multiple_times()
        test_no_entities()
        test_right_to_left_order()
        test_entity_not_in_block()
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED")
        print("="*60 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        raise
    except Exception as e:
        print(f"\n💥 UNEXPECTED ERROR: {e}\n")
        raise