# Release Notes

## Unreleased

- Breaking change: `create_page` now maps `Role` to the Notion title property
  and `Company` to rich text. Existing databases must rename their title
  property from `Company` to `Role`, or provide a `prop_name_map` override,
  before using `create_page`.
- Breaking change: `NOTION_API_KEY` and `DATABASE_ID` are now validated when
  the configuration is imported. A missing or blank value raises `RuntimeError`.
- The `create` command now exits with status 1 and creates no Notion entry when
  the target page returns an access-blocked response.
