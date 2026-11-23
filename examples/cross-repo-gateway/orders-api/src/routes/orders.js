const router = require('express').Router();

router.get('/orders', (req, res) => res.json([]));
router.get('/orders/:id', (req, res) => res.json({}));
router.post('/orders', (req, res) => res.status(201).json({}));
router.delete('/orders/:id', (req, res) => res.status(204).end());

module.exports = router;
