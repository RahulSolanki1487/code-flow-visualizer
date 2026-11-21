const express = require('express');
const ordersRouter = require('./routes/orders');

const app = express();
app.use(express.json());
app.use('/api', ordersRouter);

app.listen(3000, () => console.log('listening on 3000'));
