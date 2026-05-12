/**
 * 水仙花数（Narcissistic Number）
 * 水仙花数是指一个 n 位数 (n≥3)，它的每个位上的数字的 n 次幂之和等于它本身。
 * 例如：153 = 1³ + 5³ + 3³
 */

public class 水仙花数 {
    public static void main(String[] args) {
        System.out.println("三位数的水仙花数有：");
        for (int i = 100; i < 1000; i++) {
            if (isNarcissisticNumber(i)) {
                System.out.println(i);
            }
        }

        // 也可以扩展到更多位数
        System.out.println("\n四位数的水仙花数有：");
        for (int i = 1000; i < 10000; i++) {
            if (isNarcissisticNumber(i)) {
                System.out.println(i);
            }
        }
    }

    /**
     * 判断一个整数是否为水仙花数
     * @param num 要判断的整数
     * @return true 如果是水仙花数，否则 false
     */
    public static boolean isNarcissisticNumber(int num) {
        if (num < 0) {
            return false;
        }

        String str = String.valueOf(num);
        int n = str.length();          // 位数
        int sum = 0;
        int temp = num;

        while (temp > 0) {
            int digit = temp % 10;     // 取出个位数字
            sum += Math.pow(digit, n); // 每位数字的 n 次幂累加
            temp /= 10;                // 去掉个位
        }

        return sum == num;
    }
}
