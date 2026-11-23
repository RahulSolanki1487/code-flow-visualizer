package demo.billing;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1")
public class BillingController {

    @GetMapping("/invoices/{orderId}")
    public Invoice invoice(@PathVariable long orderId) {
        return null;
    }

    @PostMapping("/payments")
    public Payment pay(@RequestBody PaymentRequest request) {
        return null;
    }

    @PostMapping("/refunds")
    public Refund refund(@RequestBody RefundRequest request) {
        return null;
    }
}
