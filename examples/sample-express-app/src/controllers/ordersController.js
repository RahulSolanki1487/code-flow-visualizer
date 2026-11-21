const orderService = require('../services/orderService');

exports.create = async (req, res) => {
  try {
    const order = await orderService.placeOrder(req.user.id, req.body.items);
    res.status(201).json(order);
  } catch (err) {
    if (err.code === 'OUT_OF_STOCK') {
      return res.status(409).json({ error: err.message });
    }
    res.status(500).json({ error: 'internal error' });
  }
};

exports.getById = async (req, res) => {
  const order = await orderService.getOrder(req.params.id);
  res.json(order);
};
