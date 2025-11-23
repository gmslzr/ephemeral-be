from kafka import KafkaProducer

producer = KafkaProducer(bootstrap_servers=['localhost:9092'],)
producer.send('user_b94e206a-66e0-4449-982f-e8bae135935c_events',b'{"value": {"example_key": "example_value"}}')
producer.flush()

