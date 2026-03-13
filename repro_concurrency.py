
import asyncio
import threading
import json
from unittest.mock import patch, AsyncMock
from sentinel_aml.lambdas.transaction_processor import lambda_handler

def run_in_thread(i):
    event = {
        "httpMethod": "POST",
        "path": "/transactions",
        "headers": {"Content-Type": "application/json", "X-Correlation-ID": f"thread-{i}"},
        "body": json.dumps({
            "from_account_id": "ACC1",
            "to_account_id": "ACC2",
            "amount": "100.00",
            "transaction_type": "transfer",
            "currency": "USD"
        })
    }
    
    with patch('sentinel_aml.lambdas.connection_pool.NeptuneClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client.connect.return_value = None
        mock_client.get_account.return_value = {"account_id": "ACC"}
        mock_client.create_transaction.return_value = "tx123"
        mock_client.create_transaction_edge.return_value = "edge123"
        mock_client_class.return_value = mock_client
        
        try:
            response = lambda_handler(event, None)
            print(f"Thread {i} response: {response['statusCode']}")
            if response['statusCode'] != 200:
                print(f"Thread {i} body: {response['body']}")
        except Exception as e:
            print(f"Thread {i} failed with: {e}")

threads = []
for i in range(5):
    t = threading.Thread(target=run_in_thread, args=(i,))
    threads.append(t)
    t.start()

for t in threads:
    t.join()
