import asyncio
import json
import logging
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from pyflink.common.typeinfo import Types

import requests
from m4i_atlas_core import AtlasChangeMessage, ConfigStore as m4i_ConfigStore, EntityAuditAction, get_entity_by_guid, Entity
from pyflink.common.serialization import SimpleStringSchema, JsonRowSerializationSchema
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors import FlinkKafkaConsumer, FlinkKafkaProducer
from pyflink.datastream.functions import MapFunction, RuntimeContext
from set_environment import set_env

from config import config
from credentials import credentials

from m4i_data_management import make_elastic_connection
from m4i_data_management import ConfigStore as m4i_ConfigStore
from kafka import KafkaProducer
import time
from DeadLetterBoxMessage import DeadLetterBoxMesage
import traceback
import os

m4i_store = m4i_ConfigStore.get_instance()
m4i_store = m4i_ConfigStore.get_instance()


class PublishState(MapFunction):

    def open(self, runtime_context: RuntimeContext):
        m4i_store.load({**config, **credentials})
        m4i_store.load({**config, **credentials})

    def map(self, kafka_notification: str):
        try: 
            kafka_notification_json = json.loads(kafka_notification)

            if "kafka_notification" not in kafka_notification_json.keys() or "atlas_entity" not in kafka_notification_json.keys():
                raise Exception("Kafka event does not match the predefined structure.")
            
            if not kafka_notification_json.get("kafka_notification"):
                logging.warning(kafka_notification)
                logging.warning("no kafka notification")
                raise Exception("Original Kafka notification produced by Atlas is missing")

            if not kafka_notification_json.get("atlas_entity"):
                logging.warning(kafka_notification)
                logging.warning("no atlas entity")
                raise Exception("Atlas Entity in Kafka event is missing.")

            atlas_entity_json = kafka_notification_json["atlas_entity"]
            atlas_entity = json.dumps(atlas_entity_json)
            logging.warning(atlas_entity)

            atlas_entity = Entity.from_json(atlas_entity)
            
            doc_id = "{}_{}".format(atlas_entity.guid, atlas_entity.update_time)
            
            logging.warning(kafka_notification)
            logging.warning(type(atlas_entity_json))
            elastic_search_index = m4i_store.get("elastic_search_index")
            elastic = make_elastic_connection()
            elastic.index(index=elastic_search_index, id = doc_id, document=atlas_entity_json)
            elastic.close()

            return kafka_notification
        
        except Exception as e:
            exc_info = sys.exc_info()
            e = (''.join(traceback.format_exception(*exc_info)))
            logging.warning(e)

            event = DeadLetterBoxMesage(timestamp=time.time(), original_notification=kafka_notification, job="publish_state", description = (e))
            bootstrap_server_hostname, bootstrap_server_port =  m4i_store.get_many("kafka.bootstrap.server.hostname", "kafka.bootstrap.server.port")
            producer = KafkaProducer(
                bootstrap_servers=  f"{bootstrap_server_hostname}:{bootstrap_server_port}",
                value_serializer=str.encode,
                request_timeout_ms = 1000,
                api_version = (2,0,2),
                retries = 1,
                linger_ms = 1000
            )
            dead_lettter_box_topic = m4i_store.get("exception.events.topic.name") 
            producer.send(topic = dead_lettter_box_topic, value=event.to_json())
        
       
def run_publish_state_job():

    env = StreamExecutionEnvironment.get_execution_environment()
    set_env(env)
    env.set_parallelism(1)

    path = os.path.dirname(__file__) 

    # download JARs
    kafka_jar = f"file:///" + path + "/flink_jars/flink-connector-kafka-1.15.0.jar"
    kafka_client = f"file:///" + path + "/flink_jars/kafka-clients-2.2.1.jar"

    env.add_jars(kafka_jar, kafka_client)

    bootstrap_server_hostname = config.get("kafka.bootstrap.server.hostname")
    bootstrap_server_port = config.get("kafka.bootstrap.server.port")
    source_topic_name = config.get("enriched.events.topic.name")

    kafka_source = FlinkKafkaConsumer(topics = source_topic_name,
                                      properties={'bootstrap.servers': f"{bootstrap_server_hostname}:{bootstrap_server_port}",
                                                  'group.id': 'test',
                                                  'auto.offset.reset': 'earliest',
                                                  "key.deserializer": "org.apache.kafka.common.serialization.StringDeserializer",
                                                  "value.deserializer": "org.apache.kafka.common.serialization.StringDeserializer"},
                                      deserialization_schema=SimpleStringSchema()).set_commit_offsets_on_checkpoints(True).set_start_from_latest()



    data_stream = env.add_source(kafka_source)

    data_stream = data_stream.map(PublishState()).name("my_mapping")

    data_stream.print()

    env.execute("publish_state_to_elastic_search")


if __name__ == '__main__':
    logging.basicConfig(stream=sys.stdout,
                        level=logging.INFO, format="%(message)s")
    run_publish_state_job()
