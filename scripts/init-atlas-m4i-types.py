import asyncio
import os

from m4i_atlas_core import ConfigStore, create_type_defs, data_dictionary_types_def, process_types_def, \
    connectors_types_def, kubernetes_types_def

store = ConfigStore.get_instance()

store.load({
    "atlas.credentials.username": os.getenv('atlas_username'),
    "atlas.credentials.password": os.getenv('atlas_password'),
    "atlas.server.url": os.getenv('atlas_url') + "/api/atlas"
})

asyncio.run(create_type_defs(data_dictionary_types_def))
asyncio.run(create_type_defs(process_types_def))
asyncio.run(create_type_defs(connectors_types_def))
asyncio.run(create_type_defs(kubernetes_types_def))