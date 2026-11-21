const PAYMENT_URL = process.env.PAYMENT_URL || 'https://payments.example.com';

exports.charge = async (userId, amount) => {
  const res = await fetch(`${PAYMENT_URL}/charges`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ userId, amount }),
  });
  if (!res.ok) throw new Error('payment failed');
  return res.json();
};
