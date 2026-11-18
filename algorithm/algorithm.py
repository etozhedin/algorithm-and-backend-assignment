def next_term(s):
    result = ""
    count = 1

    for i in range(1, len(s)):
        if s[i] == s[i - 1]:
            count += 1
        else:
            result += str(count) + s[i - 1]
            count = 1

    result += str(count) + s[-1]

    return result

def look_and_say(n):
    s = "1"
    for i in range(n-1):
        s = next_term(s)
    return s


def get_middle_digits(result):
    mid = len(result) // 2
    return result[mid-1]+result[mid]

n = int(input("input n: "))
if 3 < n < 100:
    result = look_and_say(n)
    print(result)

    print("result:", get_middle_digits(result))
else: 
    print("invalid input: n should be more than 3 and less than 100")