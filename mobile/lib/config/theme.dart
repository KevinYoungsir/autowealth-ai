import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class AppTheme {
  // 核心颜色
  static const Color backgroundColor = Color(0xFF0A0E1A);
  static const Color surfaceColor = Color(0xFF111827);
  static const Color cardColor = Color(0xFF1A1F35);
  static const Color primaryColor = Color(0xFF00D4FF);
  static const Color secondaryColor = Color(0xFF7B2CBF);
  static const Color accentColor = Color(0xFFFF006E);

  // 信号颜色
  static const Color buyColor = Color(0xFF00F5A0);
  static const Color sellColor = Color(0xFFFF4757);
  static const Color holdColor = Color(0xFFFFA502);

  // 文字颜色
  static const Color textPrimary = Color(0xFFFFFFFF);
  static const Color textSecondary = Color(0xFF9CA3AF);
  static const Color textHint = Color(0xFF6B7280);

  static ThemeData get darkTechTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      scaffoldBackgroundColor: backgroundColor,
      colorScheme: const ColorScheme.dark(
        primary: primaryColor,
        secondary: secondaryColor,
        surface: surfaceColor,
        error: sellColor,
        onPrimary: backgroundColor,
        onSecondary: textPrimary,
        onSurface: textPrimary,
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: Colors.transparent,
        elevation: 0,
        centerTitle: true,
        titleTextStyle: GoogleFonts.orbitron(
          color: primaryColor,
          fontSize: 20,
          fontWeight: FontWeight.bold,
        ),
        iconTheme: const IconThemeData(color: primaryColor),
      ),
      cardTheme: CardTheme(
        color: cardColor,
        elevation: 4,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(
            color: primaryColor.withOpacity(0.15),
            width: 1,
          ),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: primaryColor,
          foregroundColor: backgroundColor,
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
          textStyle: GoogleFonts.roboto(
            fontSize: 16,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: primaryColor,
          textStyle: GoogleFonts.roboto(
            fontSize: 14,
            fontWeight: FontWeight.w500,
          ),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surfaceColor,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(
            color: primaryColor.withOpacity(0.3),
            width: 1,
          ),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(
            color: primaryColor.withOpacity(0.3),
            width: 1,
          ),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(
            color: primaryColor,
            width: 2,
          ),
        ),
        hintStyle: GoogleFonts.roboto(
          color: textHint,
          fontSize: 14,
        ),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      ),
      bottomNavigationBarTheme: BottomNavigationBarThemeData(
        backgroundColor: surfaceColor,
        selectedItemColor: primaryColor,
        unselectedItemColor: textHint,
        type: BottomNavigationBarType.fixed,
        selectedLabelStyle: GoogleFonts.roboto(
          fontSize: 12,
          fontWeight: FontWeight.w600,
        ),
        unselectedLabelStyle: GoogleFonts.roboto(
          fontSize: 11,
        ),
        elevation: 8,
      ),
      textTheme: TextTheme(
        headlineLarge: GoogleFonts.orbitron(
          color: textPrimary,
          fontSize: 28,
          fontWeight: FontWeight.bold,
        ),
        headlineMedium: GoogleFonts.orbitron(
          color: textPrimary,
          fontSize: 22,
          fontWeight: FontWeight.bold,
        ),
        headlineSmall: GoogleFonts.orbitron(
          color: textPrimary,
          fontSize: 18,
          fontWeight: FontWeight.w600,
        ),
        titleLarge: GoogleFonts.roboto(
          color: textPrimary,
          fontSize: 18,
          fontWeight: FontWeight.w600,
        ),
        titleMedium: GoogleFonts.roboto(
          color: textPrimary,
          fontSize: 16,
          fontWeight: FontWeight.w500,
        ),
        titleSmall: GoogleFonts.roboto(
          color: textSecondary,
          fontSize: 14,
          fontWeight: FontWeight.w500,
        ),
        bodyLarge: GoogleFonts.roboto(
          color: textPrimary,
          fontSize: 16,
        ),
        bodyMedium: GoogleFonts.roboto(
          color: textSecondary,
          fontSize: 14,
        ),
        bodySmall: GoogleFonts.roboto(
          color: textHint,
          fontSize: 12,
        ),
        labelLarge: GoogleFonts.roboto(
          color: textPrimary,
          fontSize: 14,
          fontWeight: FontWeight.w600,
        ),
        labelMedium: GoogleFonts.roboto(
          color: textSecondary,
          fontSize: 12,
          fontWeight: FontWeight.w500,
        ),
        labelSmall: GoogleFonts.roboto(
          color: textHint,
          fontSize: 10,
        ),
      ),
      dividerTheme: DividerThemeData(
        color: primaryColor.withOpacity(0.1),
        thickness: 1,
      ),
    );
  }

  /// 根据信号类型返回对应颜色
  static Color signalColor(String signal) {
    switch (signal.toLowerCase()) {
      case 'buy':
      case '买入':
      case 'strong_buy':
      case '强烈买入':
        return buyColor;
      case 'sell':
      case '卖出':
      case 'strong_sell':
      case '强烈卖出':
        return sellColor;
      case 'hold':
      case '观望':
      case 'neutral':
        return holdColor;
      default:
        return holdColor;
    }
  }

  /// 根据信号类型返回中文标签
  static String signalLabel(String signal) {
    switch (signal.toLowerCase()) {
      case 'buy':
      case '买入':
        return '买入';
      case 'strong_buy':
      case '强烈买入':
        return '强烈买入';
      case 'sell':
      case '卖出':
        return '卖出';
      case 'strong_sell':
      case '强烈卖出':
        return '强烈卖出';
      case 'hold':
      case '观望':
      case 'neutral':
        return '观望';
      default:
        return signal;
    }
  }
}
