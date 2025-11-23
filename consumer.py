from kafka import KafkaConsumer

producer = KafkaConsumer(bootstrap_servers=['localhost:9092'],)
producer.subscribe(['test_topic'])
for message in producer :
    print (message.value)

