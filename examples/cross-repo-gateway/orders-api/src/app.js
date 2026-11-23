const express = require('express');
const orders = require('./routes/orders');

const app = express();
app.use(express.json());
app.use('/api/v1', orders);

module.exports = app;
