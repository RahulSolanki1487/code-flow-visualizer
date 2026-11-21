const inventoryRepo = require('../repositories/inventoryRepo');
const orderRepo = require('../repositories/orderRepo');
const paymentClient = require('../clients/paymentClient');

exports.placeOrder = async (userId, items) => {
  const available = await inventoryRepo.reserve(items);
  if (!available) {
    const err = new Error('Some items are out of stock');
    err.code = 'OUT_OF_STOCK';
    throw err;
  }
  const total = items.reduce((sum, i) => sum + i.price * i.qty, 0);
  const payment = await paymentClient.charge(userId, total);
  return orderRepo.save({ userId, items, total, paymentId: payment.id });
};

exports.getOrder = (id) => orderRepo.findById(id);
