const router = require('express').Router();
const auth = require('../middleware/auth');
const ordersController = require('../controllers/ordersController');

router.post('/orders', auth, ordersController.create);
router.get('/orders/:id', auth, ordersController.getById);

module.exports = router;
