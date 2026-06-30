# Scout2 Plugin Notes

Scout2 is now source-aware in the GUI. Plugins should set `Listing.source` to a stable display name such as `Seabreeze`, `Gumtree`, or `eBay`.

For future plugins, keep these fields populated where possible:

- `title`
- `price`
- `price_value`
- `location`
- `url`
- `source`
- `image`
- `category`
- `description`

The cache currently groups records under each plugin name and the GUI can filter by `source`. A later migration can add stronger `source_id` / `external_id` identities without changing the user-facing workflow.


GUI note: the Listings toolbar now follows Source -> Search -> Actions, and the Source column is only visible when All Sources is selected.
