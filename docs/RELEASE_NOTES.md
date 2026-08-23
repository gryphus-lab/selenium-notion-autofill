# Release Notes

## Unreleased

- Breaking change: `create_page` now maps `Role` to the Notion title property
  and `Company` to rich text. Existing databases must rename their title
  property from `Company` to `Role`, or provide a `prop_name_map` override,
  before using `create_page`.
