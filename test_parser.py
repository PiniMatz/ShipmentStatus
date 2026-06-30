import unittest
from email_parser import parse_email

class TestEmailParser(unittest.TestCase):
    
    def test_amazon_us_parsing(self):
        subject = "Your Amazon.com order #114-1234567-1234567 has shipped"
        body = """
        Hello, your order has shipped! 
        Tracking ID: 1Z999AA10123456784 
        Carrier: UPS
        Details: Link: https://www.amazon.com/progress-tracker?orderId=114-1234567-1234567
        """
        sender = "ship-confirm@amazon.com"
        
        info = parse_email(subject, body, sender)
        self.assertEqual(info["store"], "Amazon US")
        self.assertEqual(info["order_id"], "114-1234567-1234567")
        self.assertEqual(info["tracking_number"], "1Z999AA10123456784")
        self.assertEqual(info["carrier"], "UPS")

    def test_aliexpress_parsing(self):
        subject = "Your AliExpress Order 3012345678901234 has been shipped"
        body = """
        Hi, your order 3012345678901234 is on the way.
        Tracking number: LP00611223344556
        For details visit cainiao tracking: https://global.cainiao.com/newDetail.htm?mailNoList=LP00611223344556
        """
        sender = "transaction@aliexpress.com"
        
        info = parse_email(subject, body, sender)
        self.assertEqual(info["store"], "AliExpress")
        self.assertEqual(info["order_id"], "3012345678901234")
        self.assertEqual(info["tracking_number"], "LP00611223344556")
        self.assertEqual(info["carrier"], "Cainiao")

    def test_ae_customs_parsing(self):
        subject = "Package AE040625189: at customs"
        body = "Your package AE040625189 has arrived at customs."
        sender = "notification@postal-service.com"
        
        info = parse_email(subject, body, sender)
        self.assertEqual(info["store"], "AliExpress")
        self.assertEqual(info["tracking_number"], "AE040625189")
        self.assertEqual(info["carrier"], "Cainiao")

if __name__ == "__main__":
    unittest.main()
