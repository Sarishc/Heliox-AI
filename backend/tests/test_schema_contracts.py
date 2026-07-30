from app.models.usage import UsageEvent


def test_usage_event_metadata_attribute_maps_to_migrated_column_name():
    """The ORM must use the `metadata` column created by migration 018."""
    assert UsageEvent.__table__.c.metadata.name == "metadata"
    assert UsageEvent.event_metadata.property.columns[0].name == "metadata"
